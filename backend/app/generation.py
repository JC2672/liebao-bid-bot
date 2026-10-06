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
import threading
from collections import deque
from datetime import datetime, timezone
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
        if row["status"] != "generating":
            # Confirmed live as a real bug: bulk-generate marks every
            # selected row `generating` and enqueues all of them up front,
            # so a row near the back of the batch can sit in this asyncio
            # queue for a while before the worker actually reaches it. If
            # Retry (or Remove) touched it in that window, its status
            # changed to `queued` (or it's gone) - and since nothing here
            # used to re-check before running, the worker went ahead and
            # generated it anyway, clobbering the user's retry/removal the
            # moment it finished. Bailing out here instead makes Retry
            # actually work as a cancel for a job that hasn't started yet
            # - it just never runs, rather than running anyway and winning
            # the race against whatever the user just did.
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
            # Guarded the same way `_on_status` already is above - if the
            # status changed away from `generating` while the ChatGPT call
            # was in flight (Retry/Remove can't stop a call already under
            # way, only the earlier check above can), this write loses to
            # whatever the user did instead of overwriting it.
            conn.execute(
                "UPDATE opportunities SET status = 'ready', error = NULL, "
                "resume_json = ?, staging_dir = ?, updated_at = datetime('now') "
                "WHERE id = ? AND status = 'generating'",
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
                "UPDATE opportunities SET status = 'failed', error = ?, updated_at = datetime('now') "
                "WHERE id = ? AND status = 'generating'",
                (str(exc)[:500], opp_id),
            )


# ── Background worker: one generation at a time ──────────────────────────

_queue: asyncio.Queue[tuple[int, bool]] = asyncio.Queue()
_worker_task: asyncio.Task | None = None

# In-memory run-tracking for the estimated-time-remaining feature (Queue
# screen) - mirrors routers/fetch.py's own lock-guarded progress state,
# same reasoning: ephemeral, request-visible progress that doesn't need a
# DB column, since `opportunities.updated_at` gets overwritten on every
# status change and can't tell you how long any one job actually took.
#
# A "run" is whatever's currently in flight through this one-at-a-time
# worker, across all profiles - it starts the moment the queue goes from
# idle to non-idle, and ends (stats kept, not cleared, so a brief "done"
# summary can still read them) once every pending job has finished and
# nothing new has been enqueued. `_run_pending` tracks each still-running
# job's profile so a caller can ask "how many of MINE are left".
#
# The pace estimate itself is a rolling average of the last few jobs'
# actual durations (`_recent_durations`), not a cumulative one - a plain
# cumulative average weights a slow first job (often a real ChatGPT
# cold-start) as heavily as the fiftieth, so it's slow to reflect the
# run's actual current pace and never recovers from one early outlier.
# Global, not per-profile: same worker, same pace, regardless of whose row
# it happens to be processing. Scoped to the current run, though - cleared
# in `enqueue()` on the idle->active transition, so a new run's estimate
# starts from scratch rather than riding on whatever pace the previous run
# happened to end at.
#
# Each duration is measured strictly between two real events - the moment
# the worker actually dequeues a job (`_job_started_at`) and the moment it
# finishes - never against a live "now". Confirmed live as a real bug in
# an earlier version that measured against `now()` while a job was still
# mid-flight: the estimate kept inflating every single poll tick even
# though nothing new had actually finished, because elapsed time kept
# advancing while the completed-job count didn't. Keeping `now()` entirely
# out of the duration/average math (it's only used for the still-running
# `eta_seconds` multiplication, not for measuring how long anything took)
# makes that class of bug structurally impossible to reintroduce.
_progress_lock = threading.Lock()
_run_active = False
_run_started_at: datetime | None = None
_run_finished_at: datetime | None = None
_run_profile_totals: dict[str, int] = {}
_run_pending: dict[int, str] = {}  # opp_id -> profile, for jobs not yet finished
_job_started_at: dict[int, datetime] = {}  # opp_id -> when the worker actually dequeued it
_recent_durations: deque[float] = deque(maxlen=5)  # last few completed jobs' real durations, seconds
_run_outcomes: dict[str, dict[str, int]] = {}  # profile -> {"ready"|"failed"|"cancelled": n}, this run


def enqueue(opp_id: int, open_when_ready: bool = False) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT profile FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
    profile = row["profile"] if row else ""

    global _run_active, _run_started_at, _run_finished_at, _run_profile_totals, _run_pending, _run_outcomes
    with _progress_lock:
        if not _run_active:
            _run_active = True
            _run_started_at = datetime.now(timezone.utc)
            _run_finished_at = None
            _run_profile_totals = {}
            _run_pending = {}
            _run_outcomes = {}
            # Each run estimates its own pace from scratch - leftover
            # durations from whatever last ran would otherwise make this
            # run's very first job report a stale ETA before anything
            # here has actually finished.
            _recent_durations.clear()
        _run_profile_totals[profile] = _run_profile_totals.get(profile, 0) + 1
        _run_pending[opp_id] = profile

    _queue.put_nowait((opp_id, open_when_ready))


def _mark_job_started(opp_id: int) -> None:
    with _progress_lock:
        _job_started_at[opp_id] = datetime.now(timezone.utc)


def _mark_run_job_done(opp_id: int, outcome: str | None) -> None:
    """`outcome` is the row's actual final status - `ready`/`failed` if
    generation really ran to completion, or `cancelled` if the row's
    status had already moved away from `generating` by the time the
    worker reached it (Retry/Remove while it was still waiting its turn -
    see the early-exit check in run_generation()) or the row was removed
    outright. `None` only for a row this run never heard of, which
    shouldn't happen but isn't worth raising over."""
    global _run_active, _run_finished_at
    with _progress_lock:
        profile = _run_pending.pop(opp_id, None)
        started = _job_started_at.pop(opp_id, None)
        if started is not None and outcome in ("ready", "failed"):
            # Only a real attempt's duration counts toward the pace
            # average - a cancelled job never actually ran.
            _recent_durations.append((datetime.now(timezone.utc) - started).total_seconds())
        if profile is not None and outcome is not None:
            counts = _run_outcomes.setdefault(profile, {})
            counts[outcome] = counts.get(outcome, 0) + 1
        if not _run_pending and _queue.empty():
            _run_active = False
            _run_finished_at = datetime.now(timezone.utc)


def get_progress(profile: str | None = None) -> dict:
    """Profile-scoped remaining/ETA, global rolling-average pace - see the
    module comment above `_progress_lock` for why. `remaining` only counts
    jobs still actually processing for this profile (bulk-generate flips
    every selected row to `generating` immediately, but the worker still
    works through them one at a time) - "my part of the current run," not
    "everything queued app-wide". `total_elapsed_seconds` is only set once
    the run has actually finished - a real wall-clock fact for a "done in
    Xm Ys" summary, deliberately not exposed while still running (where it
    would just be the same now()-leak this was rewritten to avoid).

    `profile=None` resolves to whichever profile the current run actually
    belongs to - the floating status widget (App.tsx) isn't scoped to any
    one tab/profile, so it has no profile of its own to ask about; it just
    wants "is anything running, and whose is it." The resolved id comes
    back as `profile` in the response. If nothing is running, resolves to
    nothing and the response reports inactive - there's no profile to
    attribute idle time to."""
    with _progress_lock:
        if profile is None:
            profile = next(iter(_run_pending.values()), None) or next(iter(_run_profile_totals), None)
        durations = list(_recent_durations)
        remaining = sum(1 for p in _run_pending.values() if p == profile) if profile else 0
        total = _run_profile_totals.get(profile, 0) if profile else 0
        started_at = _run_started_at.isoformat() if _run_started_at else None
        finished_at = _run_finished_at.isoformat() if _run_finished_at else None
        active = _run_active
        outcomes = dict(_run_outcomes.get(profile, {})) if profile else {}
        total_elapsed_seconds = (
            (_run_finished_at - _run_started_at).total_seconds()
            if not active and _run_finished_at and _run_started_at
            else None
        )

    avg_seconds_per_job = sum(durations) / len(durations) if durations else None
    eta_seconds = avg_seconds_per_job * remaining if avg_seconds_per_job is not None else None
    return {
        "active": active,
        "profile": profile,
        "completed": total - remaining,
        "total": total,
        "remaining": remaining,
        "ready": outcomes.get("ready", 0),
        "failed": outcomes.get("failed", 0),
        "cancelled": outcomes.get("cancelled", 0),
        "avg_seconds_per_job": avg_seconds_per_job,
        "eta_seconds": eta_seconds,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_elapsed_seconds": total_elapsed_seconds,
    }


async def _worker_loop() -> None:
    while True:
        opp_id, open_when_ready = await _queue.get()
        _mark_job_started(opp_id)
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
            # Read the row's actual final status rather than assuming -
            # normally `ready`/`failed` (run_generation leaves it at
            # exactly one of those), but it can also be `queued` (Retry hit
            # it before the worker got here - the early-exit check in
            # run_generation skipped it entirely, on purpose, see there)
            # or simply gone (Removed the same way). Both count as
            # `cancelled`: real work never happened, so it's neither a
            # success nor a failure.
            with get_conn() as conn:
                row = conn.execute("SELECT status FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
            status = row["status"] if row else None
            outcome = status if status in ("ready", "failed") else "cancelled"
            _mark_run_job_done(opp_id, outcome)
            _queue.task_done()


def reconcile_interrupted_jobs() -> int:
    """Called once from main.py's startup event, before anything else - any
    row still at `generating` the moment the backend boots up is
    necessarily orphaned, never a real in-flight job: this process's
    in-memory worker state (the asyncio queue, `_run_pending`, etc.) starts
    empty every time, so nothing here could legitimately be mid-generation
    before `start_worker()` below has even run once.

    Confirmed live as a real lockout: the Queue screen now treats any
    `generating` row as "a batch is running" and locks every other
    non-ready row until it clears - exactly right for a real run, but a
    stale row left over from a force-closed browser/backend (the ChatGPT
    Playwright window killed mid-call, or the server itself stopped before
    the job finished) never clears on its own, since nothing is left to
    finish it. Without this, that one leftover row locks the entire queue
    for that profile forever, with no action able to reach it either (Retry
    is deliberately locked out right along with everything else).

    Reset to `queued` - not `failed` - since nothing about what actually
    happened belongs on this row: confirmed live that an interrupted job
    never gets as far as writing a staging folder or `resume_json` (the
    disk write happens before the DB write in run_generation(), and
    neither exists for a row caught here), so there's no real failure to
    report either, just an attempt that never got anywhere. `queued`
    treats it exactly like it was never clicked - one Generate away from a
    clean attempt, no stale error note left behind to clear."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE opportunities SET status = 'queued', error = NULL, "
            "updated_at = datetime('now') WHERE status = 'generating'"
        )
        return cur.rowcount


def start_worker() -> None:
    """Called once from main.py's startup event, alongside init_db()."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
