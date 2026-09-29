"""Orchestrates one opportunity's `queued -> generating -> ready/failed`
pipeline: build a prompt from the profile's prompt.md + the JD, ask
ChatGPT for resume_json, validate it, substitute the profile's real contact
fields, render through the existing Phase 2 template/PDF pipeline
(resume_render.py), and land the result in staging - the same place
Applied (queue.py) already knows how to pick up from.

A single in-process background worker consumes an `asyncio.Queue` of
opportunity ids, one at a time - there's only one ChatGPT browser/
conversation anyway (see chatgpt_engine.py). `POST /queue/{id}/generate`
just flips status to `generating` and enqueues; the Queue screen's
existing 5s poll (already built, already handles the `generating` badge)
picks up the eventual `ready`/`failed` transition with no new frontend
polling logic needed.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pydantic

from . import chatgpt_engine
from . import profiles as profiles_module
from . import templates as templates_module
from .db import get_conn
from .models import Profile
from .resume_render import render_html, render_pdf
from .resume_schema import ResumeJson

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STAGING_DIR = DATA_DIR / "staging"

# Contact fields are asked for as literal placeholder tokens, matching
# docs/ARCHITECTURE.md's "Why this shape": contact info never enters the
# LLM's actual judgment, it's substituted by the app afterward regardless
# of what came back (see _substitute_contact below) - not a find/replace
# over the JSON text, a direct overwrite, so a stray literal "{NAME}" in
# free text elsewhere can never get mis-replaced.
_SCHEMA_INSTRUCTIONS = """Return ONLY a single JSON object (inside a ```json code fence, nothing else - no chat, no explanation before or after) matching exactly this shape:

{
  "name": "{NAME}", "title": "<a resume headline tailored to this job>", "location": "{LOCATION}",
  "phone": "{PHONE}", "email": "{EMAIL}", "linkedin": "{LINKEDIN}",
  "summary": "<2-3 sentence professional summary tailored to this job>",
  "skills": [{"category": "...", "items": "comma-separated list"}],
  "experience": [{"company": "...", "location": "...", "title": "...", "dates": "...", "project": "", "bullets": ["...", "..."]}],
  "education": [{"school": "...", "degree": "...", "year": "...", "details": ""}],
  "certifications": ["..."]
}

Keep the literal placeholder tokens {NAME}, {LOCATION}, {PHONE}, {EMAIL}, {LINKEDIN} exactly as shown above, character for character - do not fill them in with real values. Everything else should be real, tailored content."""


def build_prompt(prompt_md: str, job_description: str) -> str:
    return f"{prompt_md}\n\n---\nJob description:\n{job_description}\n\n---\n{_SCHEMA_INSTRUCTIONS}"


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def parse_resume_json(reply: str) -> ResumeJson:
    """Strip chat filler / code fences, tolerate trailing commas, validate
    structurally against ResumeJson. Raises ValueError with a readable
    message on anything that doesn't come out as a real resume - this is
    real structural validation, not the string-heuristic approach (starts
    with a tag, minimum length, no refusal phrases) a sibling project uses
    for its own free-form HTML output."""
    text = reply.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("ChatGPT's reply didn't contain a JSON object")
    candidate = _TRAILING_COMMA_RE.sub(r"\1", match.group(0))
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ChatGPT's reply wasn't valid JSON: {exc}") from exc
    try:
        return ResumeJson.model_validate(data)
    except pydantic.ValidationError as exc:
        raise ValueError(f"ChatGPT's reply didn't match the resume schema: {exc}") from exc


def _substitute_contact(resume: ResumeJson, profile: Profile) -> ResumeJson:
    return resume.model_copy(update={
        "name": profile.name,
        "location": profile.location,
        "phone": profile.phone,
        "email": profile.email,
        "linkedin": profile.linkedin,
    })


def _safe_filename(s: str) -> str:
    return "".join(c for c in s if c not in '\\/:*?"<>|').strip()


async def run_generation(opp_id: int) -> None:
    """The actual pipeline for one row. Always leaves the row at `ready` or
    `failed` - never raises, so the worker loop can't be taken down by one
    bad opportunity."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
    if row is None:
        return

    try:
        profile = profiles_module.get_profile(row["profile"])
        prompt_md = profiles_module.get_prompt(row["profile"])
        prompt = build_prompt(prompt_md, row["description"])

        reply = await chatgpt_engine.ask(prompt)
        resume = parse_resume_json(reply)
        resume = _substitute_contact(resume, profile)

        template_html = templates_module.get_html(profile.template_id)
        fields = resume.model_dump()
        html = render_html(template_html, {}, fields)
        # render_pdf() uses Playwright's *sync* API internally (fine for the
        # templates preview router, which FastAPI runs sync def handlers
        # for in a worker thread automatically) - but this function runs
        # directly on the event loop the background worker owns, and the
        # sync Playwright API raises if called from inside a running
        # asyncio loop. Hence the explicit thread here rather than a bare
        # call (confirmed live: this genuinely fails without it).
        pdf_bytes = await asyncio.to_thread(render_pdf, html)

        staging_dir = STAGING_DIR / str(opp_id)
        staging_dir.mkdir(parents=True, exist_ok=True)
        pdf_name = _safe_filename(profile.name).replace(" ", "_") or "resume"
        (staging_dir / f"{pdf_name}.pdf").write_bytes(pdf_bytes)
        (staging_dir / "JD.txt").write_text(row["description"], encoding="utf-8")

        with get_conn() as conn:
            conn.execute(
                "UPDATE opportunities SET status = 'ready', error = NULL, "
                "resume_json = ?, staging_dir = ?, updated_at = datetime('now') WHERE id = ?",
                (resume.model_dump_json(), str(staging_dir), opp_id),
            )
    except Exception as exc:  # noqa: BLE001 - land the row on `failed`, never crash the worker
        with get_conn() as conn:
            conn.execute(
                "UPDATE opportunities SET status = 'failed', error = ?, updated_at = datetime('now') WHERE id = ?",
                (str(exc)[:500], opp_id),
            )


# ── Background worker: one generation at a time ──────────────────────────

_queue: asyncio.Queue[int] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


def enqueue(opp_id: int) -> None:
    _queue.put_nowait(opp_id)


async def _worker_loop() -> None:
    while True:
        opp_id = await _queue.get()
        try:
            await run_generation(opp_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    """Called once from main.py's startup event, alongside init_db()."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
