"""Jobicy adapter - public JSON API, no login, no key.

Unlike most other feed-style sources here, Jobicy's `tag` param genuinely
filters server-side (verified: tag=salesforce returns real Salesforce-titled
postings, not the whole feed) and each job carries its own `jobGeo` field
(e.g. "USA") - a real location signal most other free sources lack.
"""
from __future__ import annotations

from datetime import datetime

import requests
from bs4 import BeautifulSoup

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://jobicy.com/api/v2/remote-jobs"


def _location(geo: str) -> str:
    geo = (geo or "").strip()
    if not geo:
        return "Remote"
    if geo.upper() in ("USA", "US"):
        return "Remote - United States"
    return f"Remote - {geo}"


def fetch_jobicy(query: str) -> list[RawPosting]:
    # Jobicy tags are single words (like RemoteOK) - use the query's first
    # word as the tag; a phrase like "Salesforce Administrator" would match
    # nothing as a literal tag.
    tag = query.strip().lower().split()[0] if query.strip() else ""
    resp = requests.get(API_URL, params={"tag": tag, "count": 50}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    postings: list[RawPosting] = []
    for job in data.get("jobs", []):
        posted_at: datetime | None = None
        if job.get("pubDate"):
            try:
                posted_at = datetime.fromisoformat(job["pubDate"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        description = BeautifulSoup(job.get("jobDescription", ""), "html.parser").get_text("\n", strip=True)
        postings.append(RawPosting(
            source="jobicy",
            external_id=str(job.get("id", job.get("jobSlug", ""))),
            url=job.get("url", ""),
            company=job.get("companyName", ""),
            title=job.get("jobTitle", ""),
            location=_location(job.get("jobGeo", "")),
            description=description or job.get("jobExcerpt", ""),
            posted_at=posted_at,
        ))
    return postings
