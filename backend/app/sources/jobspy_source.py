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


def _scrape(site_name: str, query: str) -> list[RawPosting]:
    df = scrape_jobs(
        site_name=[site_name],
        search_term=query,
        location=DEFAULT_LOCATION,
        results_wanted=DEFAULT_RESULTS,
        country_indeed="USA",
    )
    if df is None or df.empty:
        return []
    return [_row_to_posting(site_name, row) for _, row in df.iterrows()]


def fetch_linkedin(query: str) -> list[RawPosting]:
    return _scrape("linkedin", query)


def fetch_indeed(query: str) -> list[RawPosting]:
    return _scrape("indeed", query)


def fetch_zip_recruiter(query: str) -> list[RawPosting]:
    return _scrape("zip_recruiter", query)


def fetch_glassdoor(query: str) -> list[RawPosting]:
    return _scrape("glassdoor", query)


def fetch_google(query: str) -> list[RawPosting]:
    return _scrape("google", query)
