"""Part 1: Fetch. Stateless - results are returned to the client, never stored.

POST /fetch/start kicks off a fetch as a background job and returns
immediately; GET /fetch/status reports live per-source progress plus the
final result once done - the Fetch tab polls this to show a literal
checklist ticking off each source as it actually finishes, rather than a
purely decorative loading animation. This replaced one blocking POST that
returned everything at once; that shape couldn't report progress mid-flight
since the HTTP response itself didn't exist until the whole thing was over.

Single fetch at a time, same assumption as the rest of this project (one
queue worker, one ChatGPT browser, one Jobright login flow): starting a
second one while the first is still running is rejected (409), not queued
or run concurrently - the Fetch tab already disables its own controls
while a fetch is in flight, so this should only ever be hit by something
unexpected (a second tab, a retried request), not normal use.

Confirmed directly in sources/__init__.py: sources are fetched one at a
time, in order, not concurrently - worth being accurate about, since an
earlier loading-animation design here assumed otherwise. That sequential
order is exactly what the checklist now reflects truthfully.

POST /fetch/export takes the (client-side pruned) rows and returns an XLSX.
"""
from __future__ import annotations

import io
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..gates import apply_gates, dedupe_key
from ..models import FetchRequest, FetchResponse, FetchStatusResponse, GateResult, SourceProgress
from ..sources import SOURCES

router = APIRouter(prefix="/fetch", tags=["fetch"])

EXPORT_COLUMNS = [
    "source", "company", "title", "location", "url",
    "posted_at", "flags", "description",
]

# Single-job state, deliberately not keyed by a job id - there's only ever
# one fetch in flight at a time (see module docstring). Guarded by `_lock`
# since the background thread writes to it while GET /fetch/status reads
# it from a separate request/thread.
_lock = threading.Lock()
_running = False
_progress: list[SourceProgress] = []
_result: FetchResponse | None = None
_error: str | None = None


@router.post("/start")
def start_fetch(req: FetchRequest) -> dict:
    global _running, _progress, _result, _error
    with _lock:
        if _running:
            raise HTTPException(409, "A fetch is already running")
        _running = True
        _progress = [SourceProgress(name=name) for name in req.sources]
        _result = None
        _error = None

    threading.Thread(
        target=_run_job, args=(req.sources, req.query, req.posted_within_days), daemon=True,
    ).start()
    return {"started": True}


@router.get("/status", response_model=FetchStatusResponse)
def fetch_status() -> FetchStatusResponse:
    with _lock:
        return FetchStatusResponse(
            running=_running,
            sources=[p.model_copy() for p in _progress],
            result=_result,
            error=_error,
        )


def _run_job(source_names: list[str], query: str, posted_within_days: int) -> None:
    global _running, _result, _error
    try:
        postings = []
        for i, name in enumerate(source_names):
            with _lock:
                _progress[i].status = "running"

            fn = SOURCES.get(name)
            try:
                found = fn(query, posted_within_days) if fn is not None else []
                postings.extend(found)
                with _lock:
                    _progress[i].status = "done"
                    _progress[i].count = len(found)
            except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the fetch
                print(f"[sources] {name} failed: {exc}")
                with _lock:
                    _progress[i].status = "failed"

        seen: set[str] = set()
        deduped = []
        for p in postings:
            key = dedupe_key(p)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

        results: list[GateResult] = [apply_gates(p, posted_within_days) for p in deduped]
        counts = {
            "fetched": len(postings),
            "deduped": len(deduped),
            "passed": sum(1 for r in results if r.passed),
            "rejected": sum(1 for r in results if not r.passed),
        }
        with _lock:
            _result = FetchResponse(results=results, counts=counts)
    except Exception as exc:  # noqa: BLE001 - never leave `running` stuck true on an unexpected failure
        with _lock:
            _error = str(exc)[:500]
    finally:
        with _lock:
            _running = False


@router.post("/export")
def export_xlsx(rows: list[GateResult]) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = "Shortlist"
    ws.append(EXPORT_COLUMNS)
    for r in rows:
        ws.append([
            r.source, r.company, r.title, r.location, r.url,
            r.posted_at.isoformat() if r.posted_at else "",
            ", ".join(r.flags), r.description,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"shortlist-{datetime.now():%Y-%m-%d}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
