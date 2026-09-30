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
import os
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


def build_prompt_parts(prompt_md: str, name: str, location: str, phone: str, email: str,
                        linkedin: str, job_title: str, company: str, job_description: str) -> list[str]:
    """Fills in whichever of prompt.md's own placeholder tokens are
    present, with real values - the prompt is the source of truth for the
    schema and tailoring instructions, this just resolves what it's
    already asking for.

    Returns exactly two parts - `[instructions, job_description]` - sent as
    two separate chat turns rather than pasted together as one message; see
    `chatgpt_engine.ask()`'s docstring for why. A real profile's prompt.md
    already anticipates this shape on its own ("I will provide you with: 1.
    My master resume... 2. A specific job description"), with `{JD}` at the
    very end of the file - so this is just resolving that split explicitly.
    If `{JD}` sits before some trailing instructions instead (a different
    prompt.md's own convention), that trailing part is folded into the
    second turn, appended after the JD - it still needs to reach the model
    before generation happens, and there's no third turn to send it in. A
    prompt.md that doesn't use `{JD}` at all still gets the JD as its own
    second turn, just without anything to substitute in place of a token
    that was never there."""
    text = prompt_md
    for token, value in {
        "{NAME}": name, "{LOCATION}": location, "{PHONE}": phone,
        "{EMAIL}": email, "{LINKEDIN}": linkedin,
        "{JOB_TITLE}": job_title, "{COMPANY}": company,
    }.items():
        text = text.replace(token, value)
    if "{JD}" in text:
        prefix, _, suffix = text.partition("{JD}")
        if prefix.strip():
            second = f"{job_description}\n\n{suffix.strip()}" if suffix.strip() else job_description
            return [prefix.strip(), second]
    return [text.strip(), f"Job description:\n{job_description}"]


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

# ChatGPT's UI renders inline citation markers as custom elements
# (`:contentReference[...]{...}`-style); confirmed live that reading the
# page via `.innerText` (see chatgpt_engine._READ_ANSWER) leaks their raw
# source text straight into whichever string it's positioned in - pure DOM
# artifact, never real resume content, so it's stripped rather than passed
# through to the rendered PDF.
_CITATION_MARKER_RE = re.compile(r":[a-zA-Z][\w-]*reference(?:\[[^\]]*\])?\{[^}]*\}")


def _escape_raw_control_chars(text: str) -> str:
    """Replace any literal control character (raw newline, tab, etc.) found
    *inside* a JSON string literal with a single space - confirmed live as a
    real failure mode: the DOM read in chatgpt_engine._READ_ANSWER uses
    `.innerText` on a rendered <pre><code> block, and a long wrapped line in
    there can come back with a real newline character where the JSON text
    itself never had one, which `json.loads` correctly rejects ("Invalid
    control character"). A space rather than an escaped `\\n` on purpose:
    none of ResumeJson's fields are meant to contain a real line break, so
    this is a wrapped-line artifact to undo, not content to preserve - kept
    as `\\n` it would print as an abrupt break mid-sentence in the PDF. A raw
    newline *outside* a string (JSON's own pretty-print whitespace) is
    always harmless and left untouched."""
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                in_string = False
                out.append(ch)
            elif ord(ch) < 0x20:
                out.append(" ")  # wrapped-line artifact or other stray control char alike
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def parse_resume_json(reply: str) -> ResumeJson:
    """Strip chat filler / code fences, tolerate trailing commas and raw
    control characters inside strings, validate structurally against
    ResumeJson. Raises ValueError with a readable message on anything that
    doesn't come out as a real resume - this is real structural validation,
    not the string-heuristic approach (starts with a tag, minimum length,
    no refusal phrases) a sibling project uses for its own free-form HTML
    output."""
    text = reply.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("ChatGPT's reply didn't contain a JSON object")
    candidate = _TRAILING_COMMA_RE.sub(r"\1", match.group(0))
    candidate = _CITATION_MARKER_RE.sub("", candidate)
    candidate = _escape_raw_control_chars(candidate)
    candidate = _MULTISPACE_RE.sub(" ", candidate)
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


async def run_generation(opp_id: int, open_when_ready: bool = False) -> None:
    """The actual pipeline for one row. Always leaves the row at `ready` or
    `failed` - never raises, so the worker loop can't be taken down by one
    bad opportunity. The row lookup itself is inside the try too (a
    previous version had it outside, which meant a failure there - or any
    other exception this broad `except` doesn't catch - could escape and
    silently kill the whole worker loop; confirmed live as the cause of
    opportunities getting permanently stuck on `generating` with no
    browser window and no way to recover them from the UI).

    `open_when_ready`: pop the staging folder open in Explorer the moment
    this row lands on `ready` - only set for the single-row Generate button
    (see routers/queue.py), not bulk-generate, where popping open a new
    Explorer window per row as each one finishes would be disruptive rather
    than helpful."""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if row is None:
            return

        profile = profiles_module.get_profile(row["profile"])
        prompt_md = profiles_module.get_prompt(row["profile"])
        prompt_parts = build_prompt_parts(
            prompt_md, profile.name, profile.location, profile.phone, profile.email,
            profile.linkedin, row["title"], row["company"], row["description"],
        )

        def _on_status(message: str) -> None:
            # Reuses the `error` column as a general in-progress status
            # note, not just a failure message - lets the Queue screen show
            # "waiting for you to sign in" live instead of the row sitting
            # silently on `generating` for up to 5 minutes before finally
            # erroring out. Guarded to only touch the row while it's still
            # actually `generating`, in case a late callback fires after
            # the row has already moved on (e.g. the user hit Retry).
            with get_conn() as conn:
                conn.execute(
                    "UPDATE opportunities SET error = ?, updated_at = datetime('now') "
                    "WHERE id = ? AND status = 'generating'",
                    (message, opp_id),
                )

        reply = await chatgpt_engine.ask(prompt_parts, on_status=_on_status)
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

        if open_when_ready:
            try:
                os.startfile(str(staging_dir))  # noqa: S606 - Windows-only, matches "My machine only" scope
            except Exception:  # noqa: BLE001 - a failed auto-open shouldn't undo a successful generation
                pass
    except Exception as exc:  # noqa: BLE001 - land the row on `failed`, never crash the worker
        with get_conn() as conn:
            conn.execute(
                "UPDATE opportunities SET status = 'failed', error = ?, updated_at = datetime('now') WHERE id = ?",
                (str(exc)[:500], opp_id),
            )


# ── Background worker: one generation at a time ──────────────────────────

_queue: asyncio.Queue[tuple[int, bool]] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


def enqueue(opp_id: int, open_when_ready: bool = False) -> None:
    _queue.put_nowait((opp_id, open_when_ready))


async def _worker_loop() -> None:
    while True:
        opp_id, open_when_ready = await _queue.get()
        try:
            await run_generation(opp_id, open_when_ready)
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
