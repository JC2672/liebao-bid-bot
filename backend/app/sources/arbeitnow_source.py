"""Arbeitnow adapter - public JSON API, no login, no key.

No server-side search despite accepting query params that look like search
(`search`, `tags`, `q` all silently return the identical unfiltered list -
verified) - browse-only, filtered client-side here, same pattern as We Work
Remotely. Skews European (many German/EU postings); US-remote yield may be
modest, but gates.py's own location gate handles that rather than this
adapter guessing.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch_arbeitnow(query: str) -> list[RawPosting]:
    words = [w for w in query.strip().lower().split() if w]
    resp = requests.get(API_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    postings: list[RawPosting] = []
    for job in data.get("data", []):
        text = f"{job.get('title', '')} {job.get('description', '')}".lower()
        if words and not any(w in text for w in words):
            continue
        posted_at: datetime | None = None
        if job.get("created_at"):
            posted_at = datetime.fromtimestamp(job["created_at"], tz=timezone.utc)
        location = job.get("location", "")
        if job.get("remote"):
            location = f"Remote - {location}" if location else "Remote"
        postings.append(RawPosting(
            source="arbeitnow",
            external_id=job.get("slug", ""),
            url=job.get("url", ""),
            company=job.get("company_name", ""),
            title=job.get("title", ""),
            location=location,
            description=job.get("description", ""),
            posted_at=posted_at,
        ))
    return postings
