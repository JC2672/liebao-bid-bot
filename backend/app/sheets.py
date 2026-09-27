"""Google Sheets access via a service account (no OAuth login flow).

Setup (one-time, per docs/ARCHITECTURE.md):
  1. Create a Google Cloud service account, download its JSON key to
     backend/service-account.json (gitignored).
  2. Create the Sheet by hand, share it with the service account's email
     (Editor), and put the Sheet ID in each profile's profile.json.
  3. Create one tab per profile, named to match `sheet_tab`, with header row:
     Date | Company | Title | Source | Job URL
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import gspread

SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent.parent / "service-account.json"

HEADER = ["Date", "Company", "Title", "Source", "Job URL"]

_client: gspread.Client | None = None


def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        if not SERVICE_ACCOUNT_PATH.exists():
            raise RuntimeError(
                f"Missing {SERVICE_ACCOUNT_PATH}. See backend/app/sheets.py docstring for setup."
            )
        _client = gspread.service_account(filename=str(SERVICE_ACCOUNT_PATH))
    return _client


def _get_worksheet(sheet_id: str, tab_name: str) -> gspread.Worksheet:
    sh = _get_client().open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(HEADER))
        ws.append_row(HEADER)
    return ws


def get_applied_urls(sheet_id: str, tab_name: str) -> set[str]:
    """Used for dedupe on import: URLs already applied-to for this profile."""
    ws = _get_worksheet(sheet_id, tab_name)
    rows = ws.get_all_records()
    return {r.get("Job URL", "").strip() for r in rows if r.get("Job URL")}


def append_applied_row(sheet_id: str, tab_name: str, *, date: str, company: str,
                        title: str, source: str, url: str) -> None:
    ws = _get_worksheet(sheet_id, tab_name)
    ws.append_row([date, company, title, source, url])
