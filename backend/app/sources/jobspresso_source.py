"""Jobspresso adapter - plain `requests`, no login, no Cloudflare block.

Confirmed live: `jobspresso.co/?s=<query>` is plain server-rendered
WordPress HTML (a real `<article class="job_listing">` per result, WP Job
Manager plugin markup), status 200, no bot-protection wall.

A bare `s=Salesforce` query is a similarly weak search here as it was on
Jobright/Indeed/Built In, but for a different underlying reason - not a
company-name-match trap, WordPress's default search matches any word
anywhere in the post body, so almost any listing whose JD happens to
mention "Salesforce" in passing (as a tool, a client, a competitor)
matches, regardless of title (confirmed live: query "Salesforce" surfaced
"Senior Financial Analyst", "Customer Operations Manager", etc., none
Salesforce roles). Same fix as Jobright/Indeed/Built In: fan out over
SALESFORCE_TITLES instead of the caller's free text. Unlike those sources
though, this is a genuinely small site (10 results/page, single digits of
genuinely Salesforce-relevant postings at any time) - the fan-out here is
mostly about coverage of whatever phrasing the one or two real listings
happen to use, not fighting a large noise problem.

Full description IS fetched (one extra `requests` GET per title-relevant
result, same pattern as Dice) - confirmed live: the search-result card
only has a short summary paragraph, but the job's own detail page has the
real JD in a `.content-area` div, plain HTML, no extra block.

Posted date is "Month Day" with no year (e.g. "October 20") - a new
`parse_month_day` helper in `_dates.py` infers the year (a date that
hasn't happened yet this year must be from last year, since postings are
never future-dated).

No location-based filtering needed source-side: values seen live are a mix
of "Worldwide"/"Anywhere"/blank (treated as bare "Remote", same as
Jobgether's "Anywhere" convention) and specific countries/regions -
gates.py's own US-or-remote gate already handles the rest correctly.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from ..gates import _is_salesforce_relevant
from ..models import RawPosting
from ._dates import parse_month_day
from ._salesforce_titles import SALESFORCE_TITLES

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://jobspresso.co/"
PAGES_PER_TITLE = 2  # 10/page
MAX_WORKERS = 8
DESCRIPTION_WORKERS = 8


def _normalize_location(raw: str) -> str:
    loc = raw.replace("⚲", "").strip()  # "⚲" pin glyph prefix
    if not loc or loc.lower() in ("worldwide", "anywhere"):
        return "Remote"
    return f"Remote - {loc}"


def _card_to_stub(article) -> dict | None:
    title_link = article.select_one("h2.entry-title a")
    if title_link is None or not title_link.get("href"):
        return None
    author_link = article.select_one(".entry-author__link")
    company, location = "", ""
    if author_link:
        parts = author_link.get_text("|", strip=True).split("|")
        company = parts[0].strip()
        location = _normalize_location(parts[1] if len(parts) > 1 else "")
    date_el = article.select_one(".entry-date")
    posted_text = date_el.get("value", "") if date_el else ""
    post_id = (article.get("id") or "").removeprefix("post-")

    return {
        "external_id": post_id or title_link["href"],
        "url": title_link["href"],
        "title": title_link.get_text(strip=True),
        "company": company,
        "location": location,
        "posted_at": parse_month_day(posted_text) if posted_text else None,
    }


def _fetch_one_title(title: str) -> list[dict]:
    stubs: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, PAGES_PER_TITLE + 1):
        url = SEARCH_URL if page == 1 else f"{SEARCH_URL}page/{page}/"
        resp = requests.get(url, headers=HEADERS, params={"s": title}, timeout=20)
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.job_listing")
        if not articles:
            break

        new_on_page = 0
        for article in articles:
            stub = _card_to_stub(article)
            if stub is None or stub["external_id"] in seen_ids:
                continue
            seen_ids.add(stub["external_id"])
            stubs.append(stub)
            new_on_page += 1
        if new_on_page == 0:
            break
    return stubs


_DESC_RE = re.compile(r"\s+")


def _fetch_description(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException:
        return ""
    if resp.status_code != 200:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.select_one(".content-area")
    if not content:
        return ""
    return _DESC_RE.sub(" ", content.get_text(" ", strip=True)).strip()


def _fetch_one_title_safe(title: str) -> list[dict]:
    try:
        return _fetch_one_title(title)
    except requests.RequestException as exc:  # noqa: BLE001 - one title failing shouldn't kill the fetch
        print(f"[jobspresso] title={title!r} failed: {exc}")
        return []


def fetch_jobspresso(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - uses SALESFORCE_TITLES instead, see module docstring
    seen: set[str] = set()
    postings: list[RawPosting] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for batch in pool.map(_fetch_one_title_safe, SALESFORCE_TITLES):
            for stub in batch:
                if stub["external_id"] in seen:
                    continue
                seen.add(stub["external_id"])
                postings.append(RawPosting(
                    source="jobspresso",
                    external_id=stub["external_id"],
                    url=stub["url"],
                    company=stub["company"],
                    title=stub["title"],
                    location=stub["location"],
                    description="",
                    posted_at=stub["posted_at"],
                ))

    # Full JD only fetched for title-relevant candidates - most of the
    # fanned-out fetch is noise (see module docstring), no point paying for
    # a detail request that's going to be discarded anyway.
    relevant = [p for p in postings if _is_salesforce_relevant(p)]
    with ThreadPoolExecutor(max_workers=DESCRIPTION_WORKERS) as pool:
        descriptions = pool.map(_fetch_description, [p.url for p in relevant])
    for posting, description in zip(relevant, descriptions):
        posting.description = description

    return postings
