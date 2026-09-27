"""Working Nomads adapter - public JSON API, no login, no key.

No server-side filter (verified: `category`/`tag` params don't change the
result set) - it's a small feed (dozens of postings, not thousands), so
this pulls all of it and filters client-side, same pattern as We Work
Remotely/Arbeitnow.
"""
from __future__ import annotations

from datetime import datetime

import requests
from bs4 import BeautifulSoup

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


def fetch_workingnomads(query: str) -> list[RawPosting]:
    words = [w for w in query.strip().lower().split() if w]
    resp = requests.get(API_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    jobs = resp.json()

    postings: list[RawPosting] = []
    for job in jobs:
        text = f"{job.get('title', '')} {job.get('description', '')}".lower()
        if words and not any(w in text for w in words):
            continue
        posted_at: datetime | None = None
        if job.get("pub_date"):
            try:
                posted_at = datetime.fromisoformat(job["pub_date"])
            except ValueError:
                posted_at = None
        location = job.get("location", "").strip()
        postings.append(RawPosting(
            source="workingnomads",
            external_id=job.get("url", "").rstrip("/").rsplit("/", 1)[-1],
            url=job.get("url", ""),
            company=job.get("company_name", ""),
            title=job.get("title", ""),
            location=f"Remote - {location}" if location else "Remote",
            description=BeautifulSoup(job.get("description", ""), "html.parser").get_text("\n", strip=True),
            posted_at=posted_at,
        ))
    return postings
