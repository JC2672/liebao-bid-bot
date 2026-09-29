"""Shared relative-date parsing for sources that only expose "X days ago"
style text (Dice, Jobgether) rather than a real timestamp."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_month_day(text: str) -> datetime | None:
    """"October 20", no year given (Jobspresso) -> UTC datetime. Infers the
    year: a month/day that hasn't happened yet this year must be from last
    year (job postings are never future-dated), otherwise this year."""
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})$", text.strip())
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    day = int(m.group(2))
    now = datetime.now(timezone.utc)
    try:
        candidate = datetime(now.year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    if candidate > now:
        candidate = candidate.replace(year=now.year - 1)
    return candidate


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
