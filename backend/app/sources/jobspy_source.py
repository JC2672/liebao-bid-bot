"""Adapter over python-jobspy, covering LinkedIn/Indeed/ZipRecruiter/Glassdoor/Google.

JobSpy is unofficial (it scrapes aggregator sites), so results can be flaky and
rate-limited. Each function below is a thin, source-scoped wrapper so the rest
of the app never touches jobspy's DataFrame directly.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from jobspy import scrape_jobs

from ..models import RawPosting

DEFAULT_LOCATION = "United States"
DEFAULT_RESULTS = 50


def _row_to_posting(source: str, row: pd.Series) -> RawPosting:
    posted_at = row.get("date_posted")
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at)
        except ValueError:
            posted_at = None
    elif pd.isna(posted_at) if posted_at is not None else True:
        posted_at = None

    return RawPosting(
        source=source,
        external_id=str(row.get("id") or row.get("job_url") or row.get("title")),
        url=str(row.get("job_url") or ""),
        company=str(row.get("company") or ""),
        title=str(row.get("title") or ""),
        location=str(row.get("location") or ""),
        is_remote=bool(row.get("is_remote")) if not pd.isna(row.get("is_remote")) else None,
        description=str(row.get("description") or ""),
        posted_at=posted_at,
    )


def _scrape(site_name: str, query: str, location: str = DEFAULT_LOCATION) -> list[RawPosting]:
    df = scrape_jobs(
        site_name=[site_name],
        search_term=query,
        location=location,
        results_wanted=DEFAULT_RESULTS,
        country_indeed="USA",
    )
    if df is None or df.empty:
        return []
    return [_row_to_posting(site_name, row) for _, row in df.iterrows()]


def fetch_linkedin(query: str) -> list[RawPosting]:
    # "Remote only" was asked for, but neither achievable lever actually
    # narrows to *US* remote, so this stays on location="United States"
    # rather than trade US onsite/hybrid noise for worldwide noise:
    #
    # - jobspy's `is_remote=True` sends LinkedIn's real f_WT=2 filter code,
    #   but was verified live to have NO effect - an identical top-15 result
    #   set came back with and without it (checked both via the raw HTTP
    #   response and jobspy's own parser). LinkedIn's guest/anonymous search
    #   endpoint appears to simply not honor that filter anymore.
    # - location="Remote" *does* genuinely change the result set (confirmed:
    #   real remote-tagged postings), but it's worldwide-remote, not
    #   US-remote - most of what it returns is Poland/India/Vietnam/etc.
    #   roles that gates.py's US-location gate then throws away, which is a
    #   worse trade than location="United States" (every result at least
    #   US-based, even if not every one is remote).
    #
    # "Exclude Easy Apply" is not achievable at all right now: LinkedIn's own
    # search only offers an "Easy Apply ONLY" filter (f_AL=true), no exclude
    # option, and jobspy's LinkedIn scraper never populates an `easy_apply`
    # field on scraped results either - there's nothing to filter on
    # after the fact.
    return _scrape("linkedin", query)


def fetch_indeed(query: str) -> list[RawPosting]:
    return _scrape("indeed", query)


def fetch_zip_recruiter(query: str) -> list[RawPosting]:
    return _scrape("zip_recruiter", query)


def fetch_glassdoor(query: str) -> list[RawPosting]:
    return _scrape("glassdoor", query)


def fetch_google(query: str) -> list[RawPosting]:
    return _scrape("google", query)
