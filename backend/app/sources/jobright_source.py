"""Jobright adapter - plain HTTP, no login required.

Earlier research (web search only) concluded Jobright was account-gated with
no public API, but direct inspection (via a real browser, then confirmed with
plain `requests`) showed otherwise: the search page is server-rendered
(Next.js), embeds full job data for anonymous visitors in a `__NEXT_DATA__`
JSON blob (`pageProps.jobList`, with `logined: false` confirmed), and needs
no cookies or auth at all. That data blob is far richer than a DOM scrape
would give: salary range, H1B sponsorship signal, seniority, remote/hybrid
model, and full requirements - so this parses that JSON directly rather than
scraping rendered HTML.

Known limitation: the site's `&page=` query param does not paginate the SSR
payload (verified: page=2 returns the same first page) - only the first
~20 results are reachable this way. Good enough for an on-demand fetch; real
pagination would need reverse-engineering the client-side API call the page
itself makes after load.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import requests

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://jobright.ai/jobs/search"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _location(job: dict) -> str:
    primary = job.get("jobLocation") or ""
    if job.get("isRemote"):
        return f"Remote - {primary}" if primary else "Remote"
    work_model = (job.get("workModel") or "").strip()
    if work_model and work_model.lower() != "onsite":
        return f"{primary} ({work_model})" if primary else work_model
    return primary


def _description(job: dict) -> str:
    parts = [job.get("jobSummary", "")]
    if job.get("coreResponsibilities"):
        parts.append("Responsibilities:\n" + "\n".join(f"- {r}" for r in job["coreResponsibilities"]))
    if job.get("requirements"):
        parts.append("Requirements:\n" + "\n".join(f"- {r}" for r in job["requirements"]))
    return "\n\n".join(p for p in parts if p)


def fetch_jobright(query: str) -> list[RawPosting]:
    resp = requests.get(
        SEARCH_URL, headers=HEADERS, timeout=20,
        params={"keyword": query, "value": query, "searchType": "job_title", "country": "US"},
    )
    resp.raise_for_status()
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return []
    page_props = json.loads(m.group(1))["props"]["pageProps"]

    postings: list[RawPosting] = []
    for entry in page_props.get("jobList", []):
        job = entry.get("jobResult", {})
        company = entry.get("companyResult", {}).get("companyName", "")
        posted_at: datetime | None = None
        if job.get("publishTime"):
            try:
                posted_at = datetime.fromisoformat(job["publishTime"])
            except ValueError:
                posted_at = None

        postings.append(RawPosting(
            source="jobright",
            external_id=job.get("jobId", ""),
            url=job.get("url") or job.get("applyLink") or "",
            company=company,
            title=job.get("jobTitle", ""),
            location=_location(job),
            description=_description(job),
            posted_at=posted_at,
        ))
    return postings
