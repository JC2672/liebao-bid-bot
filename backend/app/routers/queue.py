"""Part 2 (queue side): import shortlisted rows, list the queue, and the
per-row actions (Open Folder, Applied, Remove, Retry).

The SQLite `opportunities` table is a work queue only - see docs/ARCHITECTURE.md.
Generation itself (Open AI Chat / API call -> PDF) is deliberately not in this
router yet; that's Phase 3. For now rows sit at `queued` until that engine exists.
"""
from __future__ import annotations

import io
import os
import shutil
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from openpyxl import load_workbook

from .. import sheets
from ..db import get_conn
from ..models import BulkIds, Opportunity
from ..profiles import get_profile

router = APIRouter(prefix="/queue", tags=["queue"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
STAGING_DIR = DATA_DIR / "staging"


def _row_to_opportunity(row) -> Opportunity:
    return Opportunity(
        id=row["id"], profile=row["profile"], company=row["company"], title=row["title"],
        location=row["location"], source=row["source"], url=row["url"],
        description=row["description"], status=row["status"], error=row["error"],
        resume_json=row["resume_json"], staging_dir=row["staging_dir"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


@router.get("", response_model=list[Opportunity])
def list_queue(profile: str) -> list[Opportunity]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM opportunities WHERE profile = ? ORDER BY created_at ASC", (profile,)
        ).fetchall()
    return [_row_to_opportunity(r) for r in rows]


@router.post("/import")
async def import_shortlist(profile: str, file: UploadFile) -> dict:
    """Accepts the XLSX exported by /fetch/export (pruned by hand in Excel),
    dedupes against the profile's Sheet tab + current queue, and inserts the rest."""
    prof = get_profile(profile)  # raises 404-able error if unknown

    content = await file.read()
    wb = load_workbook(io.BytesIO(content))
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col = {h: i for i, h in enumerate(headers)}

    try:
        applied_urls = sheets.get_applied_urls(prof.sheet_id, prof.sheet_tab)
    except RuntimeError:
        applied_urls = set()  # service account not configured yet; don't block import

    with get_conn() as conn:
        existing_urls = {
            r["url"] for r in conn.execute(
                "SELECT url FROM opportunities WHERE profile = ?", (profile,)
            ).fetchall()
        }

        inserted, skipped = 0, 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            url = str(row[col["url"]] or "").strip()
            if not url or url in applied_urls or url in existing_urls:
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO opportunities (profile, company, title, location, source, url, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile,
                    str(row[col["company"]] or ""),
                    str(row[col["title"]] or ""),
                    str(row[col["location"]] or ""),
                    str(row[col["source"]] or ""),
                    url,
                    str(row[col["description"]] or ""),
                ),
            )
            existing_urls.add(url)
            inserted += 1

    return {"inserted": inserted, "skipped": skipped}


@router.post("/{opp_id}/applied")
def mark_applied(opp_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Opportunity not found")
        opp = _row_to_opportunity(row)

    if opp.status != "ready":
        raise HTTPException(400, f"Opportunity is '{opp.status}', not ready to apply")

    prof = get_profile(opp.profile)
    safe = lambda s: "".join(c for c in s if c not in '\\/:*?"<>|').strip()
    dest = Path(prof.output_root) / f"{safe(opp.company)} - {safe(opp.title)} - {date.today():%Y-%m-%d}"
    dest.mkdir(parents=True, exist_ok=True)

    if opp.staging_dir and Path(opp.staging_dir).exists():
        for f in Path(opp.staging_dir).iterdir():
            shutil.move(str(f), dest / f.name)
        shutil.rmtree(opp.staging_dir, ignore_errors=True)

    try:
        sheets.append_applied_row(
            prof.sheet_id, prof.sheet_tab,
            date=date.today().isoformat(), company=opp.company, title=opp.title,
            source=opp.source, url=opp.url,
        )
    except RuntimeError as exc:
        raise HTTPException(500, f"Filed to disk but Sheet append failed: {exc}") from exc

    with get_conn() as conn:
        conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))

    return {"folder": str(dest)}


@router.post("/{opp_id}/remove")
def remove_opportunity(opp_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT staging_dir FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Opportunity not found")
        if row["staging_dir"] and Path(row["staging_dir"]).exists():
            shutil.rmtree(row["staging_dir"], ignore_errors=True)
        conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    return {"ok": True}


@router.post("/{opp_id}/retry")
def retry_opportunity(opp_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE opportunities SET status = 'queued', error = NULL, updated_at = datetime('now') "
            "WHERE id = ? AND status = 'failed'",
            (opp_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(400, "Opportunity is not in 'failed' state")
    return {"ok": True}


@router.post("/bulk-remove")
def bulk_remove(body: BulkIds) -> dict:
    if not body.ids:
        return {"removed": 0}
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id, staging_dir FROM opportunities WHERE id IN ({','.join('?' * len(body.ids))})",
            body.ids,
        ).fetchall()
        for row in rows:
            if row["staging_dir"] and Path(row["staging_dir"]).exists():
                shutil.rmtree(row["staging_dir"], ignore_errors=True)
        conn.execute(
            f"DELETE FROM opportunities WHERE id IN ({','.join('?' * len(body.ids))})", body.ids
        )
    return {"removed": len(rows)}


@router.post("/bulk-retry")
def bulk_retry(body: BulkIds) -> dict:
    if not body.ids:
        return {"retried": 0}
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE opportunities SET status = 'queued', error = NULL, updated_at = datetime('now') "
            f"WHERE id IN ({','.join('?' * len(body.ids))}) AND status = 'failed'",
            body.ids,
        )
    return {"retried": cur.rowcount}


@router.post("/{opp_id}/open-folder")
def open_folder(opp_id: int) -> dict:
    """Browsers can't open local folders directly - the backend does it via Explorer."""
    with get_conn() as conn:
        row = conn.execute("SELECT staging_dir FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
    if row is None or not row["staging_dir"]:
        raise HTTPException(404, "No staging folder for this opportunity yet")
    os.startfile(row["staging_dir"])  # Windows-only, matches "My machine only" scope
    return {"ok": True}
