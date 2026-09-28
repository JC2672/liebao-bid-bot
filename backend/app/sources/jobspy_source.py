"""Adapter over python-jobspy, covering LinkedIn/Indeed/ZipRecruiter/Glassdoor/Google.

JobSpy is unofficial (it scrapes aggregator sites), so results can be flaky and
rate-limited. Each function below is a thin, source-scoped wrapper so the rest
of the app never touches jobspy's DataFrame directly.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from jobspy import scrape_jobs

from ..models import RawPosting
from ._salesforce_titles import SALESFORCE_TITLES

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


def _scrape(
    site_name: str, query: str, posted_within_days: int,
    location: str = DEFAULT_LOCATION, results_wanted: int = DEFAULT_RESULTS,
) -> list[RawPosting]:
    # `hours_old` asks the site itself to filter by recency, same fix as
    # Jobright's daysAgo (see jobright_source.py's docstring): without it,
    # `results_wanted` is a fixed-size slice of whatever the site's own
    # default sort order is (usually relevance, not date), and gates.py's
    # posted-within-N-days gate then discards most of it client-side -
    # genuinely recent postings can be missed entirely if they don't also
    # rank high on relevance. Not independently verified per-site here the
    # way Jobright's daysAgo was (each site in JobSpy honors it to varying
    # degrees), but it's documented JobSpy behavior and can only help.
    df = scrape_jobs(
        site_name=[site_name],
        search_term=query,
        location=location,
        results_wanted=results_wanted,
        country_indeed="USA",
        hours_old=posted_within_days * 24,
    )
    if df is None or df.empty:
        return []
    return [_row_to_posting(site_name, row) for _, row in df.iterrows()]


def fetch_linkedin(query: str, posted_within_days: int = 7) -> list[RawPosting]:
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
    return _scrape("linkedin", query, posted_within_days)


INDEED_WORKERS = 4  # gentler than Jobright's 8 - Indeed is known to be stricter about scraping
INDEED_RESULTS_PER_TITLE = 25


def fetch_indeed(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - uses SALESFORCE_TITLES instead, see below
    # A bare "Salesforce" query is a similarly weak search on Indeed as it
    # was on Jobright (see jobright_source.py's docstring for the fuller
    # story) - confirmed live: with query="Salesforce", 50 fetched but only
    # 2 passed gates.py's relevance gate (both from the same company); with
    # query="Salesforce Developer" alone, 50 fetched and 19 passed, and
    # "Salesforce Administrator"/"Salesforce Consultant" did comparably well
    # (30 and 34 of their own fetches). So this runs the same shared title
    # list Jobright uses (SALESFORCE_TITLES) rather than the caller's free
    # text, fanned out with modest concurrency (lower than Jobright's, and a
    # smaller per-title result cap) since Indeed is known to be stricter
    # about scraping than Jobright turned out to be.
    seen_urls: set[str] = set()
    postings: list[RawPosting] = []

    def _one(title: str) -> list[RawPosting]:
        try:
            return _scrape("indeed", title, posted_within_days, results_wanted=INDEED_RESULTS_PER_TITLE)
        except Exception as exc:  # noqa: BLE001 - one title failing shouldn't kill the fetch
            print(f"[jobspy] indeed title={title!r} failed: {exc}")
            return []

    with ThreadPoolExecutor(max_workers=INDEED_WORKERS) as pool:
        for batch in pool.map(_one, SALESFORCE_TITLES):
            for posting in batch:
                if posting.url in seen_urls:
                    continue
                seen_urls.add(posting.url)
                postings.append(posting)
    return postings


def fetch_zip_recruiter(query: str, posted_within_days: int = 7) -> list[RawPosting]:
    return _scrape("zip_recruiter", query, posted_within_days)


def fetch_glassdoor(query: str, posted_within_days: int = 7) -> list[RawPosting]:
    return _scrape("glassdoor", query, posted_within_days)


def fetch_google(query: str, posted_within_days: int = 7) -> list[RawPosting]:
    return _scrape("google", query, posted_within_days)
