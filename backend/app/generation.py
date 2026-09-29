"""Orchestrates one opportunity's `queued -> generating -> ready/failed`
pipeline: fill the profile's own prompt.md placeholders with real values,
ask ChatGPT for resume_json, validate it, render through the existing
Phase 2 template/PDF pipeline (resume_render.py), and land the result in
staging - the same place Applied (queue.py) already knows how to pick up
from.

Per the user's correction: prompt.md is the single source of truth for
both the tailoring instructions *and* the exact JSON schema to return (see
a real profile's prompt.md - it already has its own "CANDIDATE" block with
`{NAME}`/`{LOCATION}`/etc. and its own "JSON SCHEMA - REQUIRED" section).
This module's job is narrower than an earlier version of it assumed: fill
in the placeholders prompt.md already defines with real values *before*
sending, trust the schema instructions already in there, and use whatever
comes back as-is - no separate instructions appended on the way in, no
overwriting contact fields on the way out.

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
from .resume_render import render_html, render_pdf
from .resume_schema import ResumeJson

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STAGING_DIR = DATA_DIR / "staging"


def build_prompt(prompt_md: str, name: str, location: str, phone: str, email: str,
                  linkedin: str, job_title: str, company: str, job_description: str) -> str:
    """Fills in whichever of prompt.md's own placeholder tokens are
    present, with real values - the prompt is the source of truth for the
    schema and tailoring instructions, this just resolves what it's
    already asking for. `{JD}` is guaranteed to end up in the prompt one
    way or another: substituted in place if prompt.md uses that token,
    appended otherwise, so a simpler prompt.md that doesn't follow this
    convention still gets the job description at all."""
    text = prompt_md
    for token, value in {
        "{NAME}": name, "{LOCATION}": location, "{PHONE}": phone,
        "{EMAIL}": email, "{LINKEDIN}": linkedin,
        "{JOB_TITLE}": job_title, "{COMPANY}": company,
    }.items():
        text = text.replace(token, value)
    if "{JD}" in text:
        text = text.replace("{JD}", job_description)
    else:
        text = f"{text}\n\n---\nJob description:\n{job_description}"
    return text


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


def _safe_filename(s: str) -> str:
    return "".join(c for c in s if c not in '\\/:*?"<>|').strip()


async def run_generation(opp_id: int) -> None:
    """The actual pipeline for one row. Always leaves the row at `ready` or
    `failed` - never raises, so the worker loop can't be taken down by one
    bad opportunity. The row lookup itself is inside the try too (a
    previous version had it outside, which meant a failure there - or any
    other exception this broad `except` doesn't catch - could escape and
    silently kill the whole worker loop; confirmed live as the cause of
    opportunities getting permanently stuck on `generating` with no
    browser window and no way to recover them from the UI)."""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if row is None:
            return

        profile = profiles_module.get_profile(row["profile"])
        prompt_md = profiles_module.get_prompt(row["profile"])
        prompt = build_prompt(
            prompt_md, profile.name, profile.location, profile.phone, profile.email,
            profile.linkedin, row["title"], row["company"], row["description"],
        )

        reply = await chatgpt_engine.ask(prompt)
        resume = parse_resume_json(reply)

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
        except asyncio.CancelledError:
            raise  # real shutdown/cancellation - let it propagate, don't swallow it
        except BaseException as exc:  # noqa: BLE001 - belt-and-suspenders: run_generation
            # already turns everything it knows how to catch into a `failed`
            # row, but this loop itself must never die regardless - if it
            # does, every opportunity enqueued after that point sits on
            # `generating` forever with nothing left to process it.
            print(f"[generation] worker loop caught an escaped exception for id={opp_id}: {exc}")
            try:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE opportunities SET status = 'failed', error = ?, updated_at = datetime('now') "
                        "WHERE id = ? AND status = 'generating'",
                        (f"Unexpected error: {exc}"[:500], opp_id),
                    )
            except Exception:  # noqa: BLE001 - even this best-effort write failing shouldn't kill the loop
                pass
        finally:
            _queue.task_done()


def start_worker() -> None:
    """Called once from main.py's startup event, alongside init_db()."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
