"""Shared relative-date parsing for sources that only expose "X days ago"
style text (Dice, Jobgether) rather than a real timestamp."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def parse_relative_date(text: str) -> datetime | None:
    """'Today', 'Yesterday', 'X days ago', 'X+ days ago' -> UTC datetime.
    Returns None for anything unrecognized (e.g. "30+ days ago" - the gate
    treats an unknown posted date as "don't reject on this alone")."""
    text = text.strip().lower()
    now = datetime.now(timezone.utc)
    if text == "today":
        return now
    if text == "yesterday":
        return now - timedelta(days=1)
    m = re.match(r"(\d+)\s*(hour|day|week|month)s?\s*ago", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"hour": timedelta(hours=n), "day": timedelta(days=n),
             "week": timedelta(weeks=n), "month": timedelta(days=n * 30)}[unit]
    return now - delta
