"""Remotive adapter - public JSON API, no login, no API key.

Remotive's terms ask that automated callers keep request volume low (a few
times a day at most) and that job URLs link back to Remotive, which this
project already does naturally: fetch only runs on demand (see
docs/ARCHITECTURE.md), and every posting's original `url` is preserved and
is what "Open Post" opens.
"""
from __future__ import annotations

from datetime import datetime

import requests
from bs4 import BeautifulSoup

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://remotive.com/api/remote-jobs"


def _normalize_location(location: str) -> str:
    """Map Remotive's free-text location into a string gates.py's location
    regexes already understand ("Remote", "Remote - United States", "Remote - X")."""
    loc = (location or "").strip()
    l = loc.lower()
    if not loc or "world" in l:
        return "Remote"
    if "usa" in l or "united states" in l:
        return "Remote - United States"
    return f"Remote - {loc}"


def fetch_remotive(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    resp = requests.get(API_URL, headers=HEADERS, params={"search": query}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    postings: list[RawPosting] = []
    for job in data.get("jobs", []):
        posted_at: datetime | None = None
        if job.get("publication_date"):
            try:
                posted_at = datetime.fromisoformat(job["publication_date"])
            except ValueError:
                posted_at = None

        postings.append(RawPosting(
            source="remotive",
            external_id=str(job.get("id", job.get("url", ""))),
            url=job.get("url", ""),
            company=job.get("company_name", ""),
            title=job.get("title", ""),
            location=_normalize_location(job.get("candidate_required_location", "")),
            description=BeautifulSoup(job.get("description", ""), "html.parser").get_text("\n", strip=True),
            posted_at=posted_at,
        ))
    return postings
