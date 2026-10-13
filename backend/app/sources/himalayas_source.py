"""Himalayas adapter - public JSON API, no login, no key.

Earlier version of this module believed the documented `/jobs/api/search?q=`
endpoint was a dead 404 (confirmed live 2026-09-27) and fell back to scanning
the ~100 most recent postings site-wide with weak client-side text matching.
Re-checked live (2026-10-13): the search endpoint is back and returns a real
HTTP 200 with genuinely filtered results - confirmed both ways (a nonsense
query returns zero jobs, a real query returns only matching ones). Rewritten
to use it directly instead of the old browse-and-scan fallback.

Two traps found live, both worth being explicit about:
- `sort=recent` looked like the obvious choice (recency matters - see
  posted_within_days), but it reorders by date INSTEAD of relevance, and a
  bare "Salesforce" query under that sort surfaces generic sales/CRM/account-
  exec roles ahead of genuinely Salesforce-development postings - the same
  company-name/CRM-general collision trap documented on Jobright/Indeed/
  Built In. The default (no `sort` param) ranks by relevance instead, and a
  bare "Salesforce" query under that default is still noisy, but a real role
  title ("Salesforce Developer", "Salesforce Administrator") comes back
  clean (checked live, 50+ results, zero off-topic titles) - so this fans
  out over the active field's title_list the same way those other sources
  already do, rather than using query_term directly, and leaves `sort`
  unset. Recency is handled downstream by gates.py's own posted-within-N-
  days gate instead, same as every title-list-fan-out source.
- Pagination here is a plain `page=` param (1-indexed), confirmed live
  against a sibling local project's own Himalayas integration
  (brightstar-sf-job-capture/src/himalayas/search.js) - NOT the `cursor`/
  `nextCursor` scheme the *browse* endpoint (`/jobs/api`, no longer used
  here) exposes, and NOT `offset` either (confirmed live: offset=20/40/60/80
  on the search endpoint returned the exact same page-1 results every time,
  a dead param this endpoint silently ignores).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import FieldConfig, RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://himalayas.app/jobs/api/search"
PAGES_PER_TITLE = 2  # ~20/page
MAX_WORKERS = 8


def _location(job: dict) -> str:
    """Formatted as 'Remote - <restrictions>' so gates.py's existing
    US-location regex can tell a US-restricted posting from any other."""
    restrictions = job.get("locationRestrictions") or []
    names = [r if isinstance(r, str) else (r.get("name") or r.get("slug", "")) for r in restrictions]
    names = [n for n in names if n]
    return f"Remote - {', '.join(names)}" if names else "Remote"


def _job_to_posting(job: dict) -> RawPosting:
    posted_at: datetime | None = None
    if job.get("pubDate"):  # Unix epoch seconds, not an ISO string
        try:
            posted_at = datetime.fromtimestamp(job["pubDate"], tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            posted_at = None
    return RawPosting(
        source="himalayas",
        external_id=str(job.get("guid", ""))[-120:],
        url=job.get("applicationLink", ""),
        company=job.get("companyName", ""),
        title=job.get("title", ""),
        location=_location(job),
        description=BeautifulSoup(job.get("description", ""), "html.parser").get_text("\n", strip=True),
        posted_at=posted_at,
    )


def _fetch_one_title(title: str) -> list[RawPosting]:
    postings: list[RawPosting] = []
    for page in range(1, PAGES_PER_TITLE + 1):
        try:
            resp = requests.get(SEARCH_URL, params={"q": title, "page": page}, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
        except (requests.RequestException, ValueError):
            break
        if not jobs:
            break
        postings.extend(_job_to_posting(j) for j in jobs)
    return postings


def fetch_himalayas(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    titles = field.title_list or [field.query_term]
    seen: set[str] = set()
    postings: list[RawPosting] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for batch in pool.map(_fetch_one_title, titles):
            for posting in batch:
                if posting.external_id in seen:
                    continue
                seen.add(posting.external_id)
                postings.append(posting)
    return postings
