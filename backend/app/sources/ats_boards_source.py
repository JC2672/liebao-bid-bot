"""Greenhouse / Lever / Ashby adapters - direct per-company public JSON APIs,
no login, no key. Unlike every other source here, these have no cross-company
search: each is one call per company's own board (`boards-api.greenhouse.io`,
`api.lever.co`, `api.ashbyhq.com`), so getting broad coverage means fanning
out over a list of companies rather than one query.

`query` is intentionally unused, same as We Work Remotely - gates.py's title/
description relevance filter is what actually decides Salesforce relevance
here, run over every job every company in the list has open (any company
large enough to run its own Salesforce business-systems team can have a
"Salesforce Administrator" opening, whether or not the company itself has
anything to do with Salesforce as a product).

COMPANY_BOARDS below is NOT copied from any other project - every single
token was verified live (HTTP 200, non-empty job list) before being added.
A prior draft, based on a sibling local project's own list, turned out to be
badly stale: only 63 of 192 tokens tried actually resolved (Lever especially:
2 of 52). Companies migrate ATS providers over time, so this list will drift
too - re-validate before trusting an old copy of it.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from ..models import RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_WORKERS = 16

# Verified live (2026-09-27): each token below returned a real, non-empty
# job list at the time of checking. Extend freely, but verify new entries
# the same way rather than assuming a token is still valid.
GREENHOUSE_BOARDS = [
    "6sense", "affirm", "airbnb", "airtable", "amplitude", "anthropic", "apolloio",
    "asana", "block", "boxinc", "braze", "brex", "calendly", "celigo", "chime",
    "cloudflare", "coinbase", "conga", "coursera", "databricks", "datadog",
    "discord", "dropbox", "duolingo", "elastic", "figma", "flexport", "gitlab",
    "gusto", "instacart", "intercom", "iterable", "klaviyo", "launchdarkly",
    "lyft", "mercury", "mixpanel", "mongodb", "okta", "pendo", "pinterest",
    "qualtrics", "reddit", "robinhood", "salesloft", "samsara", "smartsheet",
    "sofi", "stripe", "thoughtworks", "twilio", "workato", "zoominfo",
]
LEVER_BOARDS = ["outreach", "palantir"]
ASHBY_BOARDS = [
    "gearset", "linear", "notion", "openai", "plaid", "ramp", "snowflake", "vanta",
]


def _fetch_greenhouse_one(token: str) -> list[RawPosting]:
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        params={"content": "true"}, headers=HEADERS, timeout=15,
    )
    if resp.status_code != 200:
        return []
    postings = []
    for job in resp.json().get("jobs", []):
        posted_at = None
        if job.get("updated_at"):
            try:
                posted_at = datetime.fromisoformat(job["updated_at"])
            except ValueError:
                posted_at = None
        postings.append(RawPosting(
            source="greenhouse", external_id=str(job.get("id", "")),
            url=job.get("absolute_url", ""),
            company=job.get("company_name", token),
            title=job.get("title", ""),
            location=(job.get("location") or {}).get("name", ""),
            description=job.get("content", ""),
            posted_at=posted_at,
        ))
    return postings


def _fetch_lever_one(token: str) -> list[RawPosting]:
    resp = requests.get(
        f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"},
        headers=HEADERS, timeout=15,
    )
    if resp.status_code != 200:
        return []
    postings = []
    for job in resp.json():
        categories = job.get("categories") or {}
        posted_at = None
        if job.get("createdAt"):
            posted_at = datetime.fromtimestamp(job["createdAt"] / 1000)
        location = categories.get("location") or job.get("country") or ""
        postings.append(RawPosting(
            source="lever", external_id=str(job.get("id", "")),
            url=job.get("hostedUrl", ""), company=token, title=job.get("text", ""),
            location=location, description=job.get("descriptionPlain", ""),
            posted_at=posted_at,
        ))
    return postings


def _fetch_ashby_one(token: str) -> list[RawPosting]:
    resp = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{token}", headers=HEADERS, timeout=15,
    )
    if resp.status_code != 200:
        return []
    postings = []
    for job in resp.json().get("jobs", []):
        posted_at = None
        if job.get("publishedAt"):
            try:
                posted_at = datetime.fromisoformat(job["publishedAt"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        location = job.get("location", "")
        if job.get("isRemote"):
            location = f"Remote - {location}" if location else "Remote"
        postings.append(RawPosting(
            source="ashby", external_id=str(job.get("id", "")),
            url=job.get("jobUrl") or job.get("applyUrl", ""), company=token,
            title=job.get("title", ""), location=location,
            description=job.get("descriptionPlain", ""), posted_at=posted_at,
        ))
    return postings


def _fan_out(tokens: list[str], fetch_one) -> list[RawPosting]:
    """One slow/failing company board (timeout, transient 5xx, etc.) must
    not sink the whole batch - the rest still resolve normally."""
    def safe(token: str) -> list[RawPosting]:
        try:
            return fetch_one(token)
        except Exception as exc:  # noqa: BLE001
            print(f"[ats_boards] {token} failed: {exc}")
            return []

    postings: list[RawPosting] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for result in pool.map(safe, tokens):
            postings.extend(result)
    return postings


def fetch_greenhouse(query: str) -> list[RawPosting]:  # noqa: ARG001 - fan-out, no query param
    return _fan_out(GREENHOUSE_BOARDS, _fetch_greenhouse_one)


def fetch_lever(query: str) -> list[RawPosting]:  # noqa: ARG001
    return _fan_out(LEVER_BOARDS, _fetch_lever_one)


def fetch_ashby(query: str) -> list[RawPosting]:  # noqa: ARG001
    return _fan_out(ASHBY_BOARDS, _fetch_ashby_one)
