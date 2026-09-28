"""Dice.com adapter.

Dice's own job-search API (job-search-api.svc.dhigroupinc.com) was shut down
years ago and is not publicly reachable. The site's search results page is
still plain server-rendered HTML with no login wall, so this scrapes that
page directly. Selectors are tied to Dice's current markup (data-testid
attributes where available) and WILL break if Dice redesigns the page -
that's the tradeoff of having no official API here.

Full job description text is NOT fetched per listing (that would be one
extra request per result); gating runs on title + location only for this
source, which is enough for the Salesforce/US-Remote hard gates.
"""
from __future__ import annotations

from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from ..models import RawPosting
from ._dates import parse_relative_date

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_PAGES = 5


def fetch_dice(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    postings: list[RawPosting] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"https://www.dice.com/jobs?q={quote(query)}&location=United+States&page={page}"
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('div[data-testid="job-card"]')
        if not cards:
            break

        for card in cards:
            link = card.select_one('a[data-testid="job-search-job-detail-link"]')
            company_p = card.select_one('p[data-testid="job-card-company-name"]')
            if link is None or not link.get("href"):
                continue

            # The location/posted-date line has no data-testid; distinguish it
            # from the company-name <p> by its exact class list.
            loc_p = card.find(
                "p", class_=lambda c: c == "mb-0 text-sm font-normal text-foreground-light"
            )
            location, posted_text = "", ""
            if loc_p:
                parts = loc_p.get_text(" ", strip=True).split("•")  # "•"
                location = parts[0].strip()
                posted_text = parts[1].strip() if len(parts) > 1 else ""

            job_id = link["href"].rsplit("/", 1)[-1]
            postings.append(RawPosting(
                source="dice",
                external_id=job_id,
                url=f"https://www.dice.com{link['href']}",
                company=company_p.get_text(strip=True) if company_p else "",
                title=link.get("aria-label") or link.get_text(strip=True),
                location=location,
                description="",
                posted_at=parse_relative_date(posted_text) if posted_text else None,
            ))
    return postings
