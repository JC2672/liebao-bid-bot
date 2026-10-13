"""Jobicy adapter - public JSON API, no login, no key.

Unlike most other feed-style sources here, Jobicy's `tag` param genuinely
filters server-side (verified: tag=salesforce returns real Salesforce-
related postings, not the whole feed) and each job carries its own `jobGeo`
field (e.g. "USA") - a real location signal most other free sources lack.

A single `tag=salesforce` (this module's earlier approach - just the active
field's query term, lowercased to one word) leaves real coverage on the
table: checked live (2026-10-13) against a sibling local project's own tag
list (`salesforce`/`crm`/`mulesoft`/`apex`) - `crm` only overlaps 16 of its
50 results with `salesforce`'s own 50, meaning 34 of them are postings
`tag=salesforce` alone would never see at all (not filtered out downstream,
just never fetched in the first place - the same class of bug Jobright's
pre-fix capped-page problem was). `mulesoft`/`apex` return far fewer results
each but ones genuinely missed by the broader tags too (e.g. "Salesforce
Developer (US-Remote)" only turned up under `mulesoft`). So this fans out
over all four tags and dedupes, same pattern as the title-list fan-out
sources - `tag` itself takes a single site-vocabulary word, not a free-text
phrase, so field.title_list's full role-title strings don't apply here the
way they do on Jobright/Built In/Jobspresso.

`count=100` (not 50) - confirmed live this isn't capped at some lower
server-side max.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from ..models import FieldConfig, RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://jobicy.com/api/v2/remote-jobs"
TAGS = ["salesforce", "crm", "mulesoft", "apex"]
MAX_WORKERS = 4


def _location(geo: str) -> str:
    geo = (geo or "").strip()
    if not geo:
        return "Remote"
    if geo.upper() in ("USA", "US"):
        return "Remote - United States"
    return f"Remote - {geo}"


def _job_to_posting(job: dict) -> RawPosting:
    posted_at: datetime | None = None
    if job.get("pubDate"):
        try:
            posted_at = datetime.fromisoformat(job["pubDate"].replace("Z", "+00:00"))
        except ValueError:
            posted_at = None
    description = BeautifulSoup(job.get("jobDescription", ""), "html.parser").get_text("\n", strip=True)
    return RawPosting(
        source="jobicy",
        external_id=str(job.get("id", job.get("jobSlug", ""))),
        url=job.get("url", ""),
        company=job.get("companyName", ""),
        title=job.get("jobTitle", ""),
        location=_location(job.get("jobGeo", "")),
        description=description or job.get("jobExcerpt", ""),
        posted_at=posted_at,
    )


def _fetch_one_tag(tag: str) -> list[RawPosting]:
    resp = requests.get(API_URL, params={"tag": tag, "count": 100}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return [_job_to_posting(j) for j in resp.json().get("jobs", [])]


def fetch_jobicy(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - fixed tag list, not field.title_list (see module docstring); no server-side date filter either
    seen: set[str] = set()
    postings: list[RawPosting] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for batch in pool.map(_fetch_one_tag, TAGS):
            for posting in batch:
                if posting.external_id in seen:
                    continue
                seen.add(posting.external_id)
                postings.append(posting)
    return postings
