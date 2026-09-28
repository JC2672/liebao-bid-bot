"""Himalayas adapter - public JSON API, no login, no key.

Himalayas' own docs (and its published OpenAPI spec at
himalayas.app/docs/openapi.json) describe a `/jobs/api/search` endpoint with
a `q` keyword param - but that endpoint returns a genuine live HTTP 404 as of
2026-09-27, confirmed several ways (bare path with zero params, a real
browser via CDP, and a cache-busting query param that forced Cloudflare past
its edge cache to Himalayas' own origin - still 404). Their docs are simply
ahead of what's actually deployed. Only the browse endpoint (`/jobs/api`,
cursor-paginated, no search) is live, so this pulls a few pages of the most
recent postings and filters client-side - the same pattern used for We Work
Remotely and RemoteOK's fallback. Revisit if/when `/search` comes back.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://himalayas.app/jobs/api"
MAX_PAGES = 5  # 20/page - 100 most recent postings scanned


def _location(job: dict) -> str:
    """Formatted as 'Remote - <restrictions>' so gates.py's existing
    US-location regex can tell a US-restricted posting from any other."""
    restrictions = job.get("locationRestrictions") or []
    names = [r if isinstance(r, str) else (r.get("name") or r.get("slug", "")) for r in restrictions]
    names = [n for n in names if n]
    return f"Remote - {', '.join(names)}" if names else "Remote"


def fetch_himalayas(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    words = [w for w in query.strip().lower().split() if w]
    postings: list[RawPosting] = []
    cursor = None
    for _ in range(MAX_PAGES):
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        jobs = data.get("jobs", [])
        if not jobs:
            break

        for job in jobs:
            text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            if words and not any(w in text for w in words):
                continue
            posted_at: datetime | None = None
            if job.get("pubDate"):  # Unix epoch seconds, not an ISO string
                try:
                    posted_at = datetime.fromtimestamp(job["pubDate"], tz=timezone.utc)
                except (ValueError, OSError):
                    posted_at = None
            postings.append(RawPosting(
                source="himalayas",
                external_id=str(job.get("guid", ""))[-120:],
                url=job.get("applicationLink", ""),
                company=job.get("companyName", ""),
                title=job.get("title", ""),
                location=_location(job),
                description=BeautifulSoup(job.get("description", ""), "html.parser").get_text("\n", strip=True),
                posted_at=posted_at,
            ))

        cursor = data.get("nextCursor")
        if not cursor:
            break
    return postings
