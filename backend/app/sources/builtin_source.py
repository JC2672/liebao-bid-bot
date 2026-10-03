"""Built In adapter - plain `requests`, no login, no Playwright needed.

Added per the user's ask: a sibling local project already covers Built In,
using Playwright to render the search page and then visit every job's own
detail page for the real description. Neither turned out necessary here,
confirmed live: `https://builtin.com/jobs/remote?search=...` is plain
server-rendered HTML (status 200, no Cloudflare block, no client-side
hydration needed for content), and - unlike the sibling's per-job detail
visit - each search-results card *already* embeds a real description
summary, work-arrangement badge, location, posted-date and top-skills list
inline, so a single request per page covers everything; no per-listing
follow-up request needed the way Dice's does.

A bare `search=Salesforce` query is the same trap seen on Jobright/Indeed/
Built In's own listing skews sales roles that merely require Salesforce
CRM experience ("Field Sales Representative", "Territory Account
Executive") - confirmed live: 25/25 results for a bare "Salesforce" query
were sales titles, vs. genuinely relevant results (Salesforce Developer,
Salesforce Solution Engineer, etc.) for "Salesforce Developer" alone. So
this fans out over the shared SALESFORCE_TITLES list instead of the
caller's free text, same fix as Jobright/Indeed.

Uses the `/jobs/remote` listing specifically (not `/jobs`), which scopes
every result to remote-eligible roles by construction - confirmed live,
every card's work-arrangement badge was "Remote" or "In-Office or Remote"
(never "Hybrid"/"Onsite"-only), so this already satisfies "work model =
Remote" without needing extra client-side filtering the way Greenhouse/
Lever/Ashby did.

`daysSinceUpdated` is a genuine server-side recency filter - confirmed
live scaling sensibly with a fixed query (0/9/25 results for 1/7/30 days).

Pagination is a `page=` URL param - confirmed live: page 1 and page 2 for
the same query returned zero overlapping job IDs.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from ..models import FieldConfig, RawPosting
from ._dates import parse_relative_date

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://builtin.com/jobs/remote"
PAGES_PER_TITLE = 2  # 25/page
MAX_WORKERS = 8


def _badge_text(card, icon_class: str) -> str:
    icon = card.select_one(f"i.{icon_class}")
    if not icon:
        return ""
    wrapper = icon.find_parent("div")
    if not wrapper:
        return ""
    sib = wrapper.find_next_sibling()
    return sib.get_text(strip=True) if sib else ""


def _company(card) -> str:
    link = card.select_one('a[data-id="company-title"]')
    return link.get_text(strip=True) if link else ""


def _card_to_posting(card) -> RawPosting | None:
    title_link = card.select_one('a[data-id="job-card-title"]')
    if title_link is None or not title_link.get("href"):
        return None
    href = title_link["href"]
    job_id = href.rstrip("/").rsplit("/", 1)[-1]

    desc_el = card.select_one("div.fs-sm.fw-regular.mb-md.text-gray-04")
    posted_text = _badge_text(card, "fa-clock")

    return RawPosting(
        source="builtin",
        external_id=job_id,
        url=f"https://builtin.com{href}",
        company=_company(card),
        title=title_link.get_text(strip=True),
        location=_badge_text(card, "fa-location-dot"),
        description=desc_el.get_text(strip=True) if desc_el else "",
        posted_at=parse_relative_date(posted_text) if posted_text else None,
    )


def _fetch_one_title(title: str, posted_within_days: int) -> list[RawPosting]:
    postings: list[RawPosting] = []
    seen_ids: set[str] = set()
    for page in range(1, PAGES_PER_TITLE + 1):
        params = {"search": title, "daysSinceUpdated": posted_within_days}
        if page > 1:
            params["page"] = page
        resp = requests.get(f"{SEARCH_URL}?{urlencode(params)}", headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('div[data-id="job-card"]')
        if not cards:
            break

        new_on_page = 0
        for card in cards:
            posting = _card_to_posting(card)
            if posting is None or posting.external_id in seen_ids:
                continue
            seen_ids.add(posting.external_id)
            postings.append(posting)
            new_on_page += 1
        if new_on_page == 0:
            break
    return postings


def fetch_builtin(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - uses field.title_list instead, see module docstring
    seen: set[str] = set()
    postings: list[RawPosting] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for batch in pool.map(
            lambda t: _fetch_one_title(t, posted_within_days), field.title_list
        ):
            for posting in batch:
                if posting.external_id in seen:
                    continue
                seen.add(posting.external_id)
                postings.append(posting)
    return postings
