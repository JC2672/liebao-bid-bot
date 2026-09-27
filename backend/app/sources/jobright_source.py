"""Jobright adapter - plain HTTP, works with or without login.

Earlier research (web search only) concluded Jobright was account-gated with
no public API, but direct inspection (via a real browser, then confirmed with
plain `requests`) showed otherwise for anonymous visitors: the search page is
server-rendered (Next.js) and embeds job data in a `__NEXT_DATA__` JSON blob
(`pageProps.jobList`), no cookies or auth needed. That's rich data (salary
range, H1B signal, seniority, remote/hybrid model, requirements) but capped
at the first ~20 results - `&page=` doesn't paginate the SSR payload, and
(confirmed directly: scrolled, watched every network request, checked every
button) anonymous visitors have no "Next"/"Load more"/infinite-scroll at all
to click through instead, unlike Talent.com.

If a login session has been saved (see jobright_session.py - a dedicated
Playwright-managed Chromium profile, not the user's own daily browser), this
uses the real internal API those saved cookies unlock instead
(`/swan/recommend/search`, paginated via `position`), which is what the
site's own JS uses once logged in. Both paths return the same `jobResult`/
`companyResult` job shape, so one mapping function serves both.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import requests

from .. import jobright_session
from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://jobright.ai/jobs/search"
API_URL = "https://jobright.ai/swan/recommend/search"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
MAX_AUTHENTICATED_PAGES = 5  # 20/page


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


def _entry_to_posting(entry: dict) -> RawPosting:
    job = entry.get("jobResult", {})
    company = entry.get("companyResult", {}).get("companyName", "")
    posted_at: datetime | None = None
    if job.get("publishTime"):
        try:
            posted_at = datetime.fromisoformat(job["publishTime"])
        except ValueError:
            posted_at = None
    return RawPosting(
        source="jobright",
        external_id=job.get("jobId", ""),
        url=job.get("url") or job.get("applyLink") or "",
        company=company,
        title=job.get("jobTitle", ""),
        location=_location(job),
        description=_description(job),
        posted_at=posted_at,
    )


def _fetch_anonymous(query: str) -> list[RawPosting]:
    resp = requests.get(
        SEARCH_URL, headers=HEADERS, timeout=20,
        params={"keyword": query, "value": query, "searchType": "job_title", "country": "US"},
    )
    resp.raise_for_status()
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return []
    page_props = json.loads(m.group(1))["props"]["pageProps"]
    return [_entry_to_posting(e) for e in page_props.get("jobList", [])]


def _search_body(query: str, position: int) -> dict:
    return {
        "searchType": "job_title", "value": query,
        "jobTaxonomyList": [{"taxonomyId": "00-00-00", "title": query}],
        "country": "US", "jobTypes": [], "seniority": [], "workModel": [],
        "locations": [], "companies": [], "isH1BOnly": False, "companyCategory": None,
        "annualSalaryMinimum": None, "roleType": None, "companyStages": None, "skills": [],
        "excludedCompanies": [], "excludedSkills": None, "excludeStaffingAgency": False,
        "minYearsOfExperienceRange": None, "excludeCompanyCategory": [],
        "excludeSecurityClearance": False, "excludeUsCitizen": False,
        "daysAgo": None, "refresh": True, "position": position, "sortCondition": 0,
    }


def _fetch_authenticated(query: str, cookie_header: str) -> list[RawPosting]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "x-client-type": "web",
        "user-agent": HEADERS["User-Agent"],
        "cookie": cookie_header,
    }
    postings: list[RawPosting] = []
    for page in range(MAX_AUTHENTICATED_PAGES):
        position = page * 20
        resp = requests.post(
            API_URL,
            params={"searchType": "job_title", "refresh": "true", "count": 20,
                    "position": position, "sortCondition": 0},
            headers=headers, json=_search_body(query, position), timeout=20,
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data.get("success"):
            break
        job_list = data.get("result", {}).get("jobList", [])
        if not job_list:
            break
        postings.extend(_entry_to_posting(e) for e in job_list)
    return postings


def fetch_jobright(query: str) -> list[RawPosting]:
    cookie_header = jobright_session.get_cookie_header()
    if cookie_header and jobright_session.check_session():
        return _fetch_authenticated(query, cookie_header)
    return _fetch_anonymous(query)
