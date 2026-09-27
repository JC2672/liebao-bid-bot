"""Part 1: Fetch. Stateless - results are returned to the client, never stored.

POST /fetch runs sources -> gates and returns the results table.
POST /fetch/export takes the (client-side pruned) rows and returns an XLSX.
"""
from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..gates import apply_gates, dedupe_key
from ..models import FetchRequest, FetchResponse, GateResult
from ..sources import fetch_all

router = APIRouter(prefix="/fetch", tags=["fetch"])

EXPORT_COLUMNS = [
    "source", "company", "title", "location", "url",
    "posted_at", "flags", "description",
]


@router.post("", response_model=FetchResponse)
def run_fetch(req: FetchRequest) -> FetchResponse:
    postings = fetch_all(req.sources, req.query)

    seen: set[str] = set()
    deduped = []
    for p in postings:
        key = dedupe_key(p)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    results: list[GateResult] = [apply_gates(p, req.posted_within_days) for p in deduped]

    counts = {
        "fetched": len(postings),
        "deduped": len(deduped),
        "passed": sum(1 for r in results if r.passed),
        "rejected": sum(1 for r in results if not r.passed),
    }
    return FetchResponse(results=results, counts=counts)


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
