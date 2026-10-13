"""SQLite access for the `opportunities` work queue.

This is intentionally the only table in the system (see docs/ARCHITECTURE.md
"Why this shape"). Fetch results are never persisted here; only opportunities
that have been shortlisted and imported for a specific profile live in this
table, and only until they are applied (row deleted) or removed.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "queue.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    resume_json TEXT,
    staging_dir TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_opportunities_profile_status
    ON opportunities(profile, status);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coldef: str) -> None:
    """`CREATE TABLE IF NOT EXISTS` above only creates the table on a brand
    new database - it does nothing for a column added later to a table
    that already exists (this project's real one, with real rows, already
    did). This is the idempotent `ALTER TABLE` that actually lands it."""
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Added for Quick Apply (see routers/queue.py's quick_apply) - a
        # manually-entered posting's own stated post date, since nothing
        # fetched it to know one otherwise.
        _ensure_column(conn, "opportunities", "posted_at", "TEXT")
        # Set once, at import time (CSV/XLSX upload and Fetch's "Queue
        # after fetch"), when the row's company already shows up in the
        # profile's Applied sheet - a flag for the Queue table to surface,
        # not a block (see routers/queue.py's _dedupe_and_insert).
        _ensure_column(conn, "opportunities", "company_seen", "INTEGER NOT NULL DEFAULT 0")
        # JSON-encoded list of {title, date, stage} - the past application(s)
        # at this row's company, as of import time, for the Queue table's
        # hover-for-detail on the company_seen flag above. NULL/"[]" when
        # company_seen is 0.
        _ensure_column(conn, "opportunities", "company_seen_detail", "TEXT")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
