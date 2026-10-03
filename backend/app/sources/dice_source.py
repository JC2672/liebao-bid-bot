"""Dice.com adapter.

Dice's own job-search API (job-search-api.svc.dhigroupinc.com) was shut down
years ago and is not publicly reachable. The site's search results page is
still plain server-rendered HTML with no login wall, so this scrapes that
page directly. Selectors are tied to Dice's current markup (data-testid
attributes where available) and WILL break if Dice redesigns the page -
that's the tradeoff of having no official API here.

Unlike the search page, a bare "Salesforce" query here isn't a trap -
checked live: 142 of 166 results had a Salesforce-relevant title (no
company-name-match problem like Jobright/Indeed had), so this keeps using
the caller's free-text query rather than SEED_TITLES.

Full job description IS fetched, one extra plain `requests` GET per
title-relevant result (checked how a sibling local project handles this -
it uses Playwright per listing, but that's not actually necessary here:
each Dice job-detail page embeds a `application/ld+json` JobPosting block
in the raw server-rendered HTML with the real description, reachable with
plain `requests` - no Cloudflare block, confirmed live, status 200).
Fetched only for postings that already pass the title-relevance gate,
not all of them, since most of a page's results won't - no point paying
for a detail request that's going to be discarded anyway.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .. import gates
from ..models import FieldConfig, RawPosting
from ._dates import parse_relative_date

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_PAGES = 5
DESCRIPTION_WORKERS = 8
LD_JSON_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("</p>", "\n\n")
    text = HTML_TAG_RE.sub("", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _fetch_description(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException:
        return ""
    if resp.status_code != 200:
        return ""
    m = LD_JSON_RE.search(resp.text)
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""
    if isinstance(data, list):
        data = next((d for d in data if d.get("@type") == "JobPosting"), {})
    return _strip_html(data.get("description", ""))


def fetch_dice(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    # `location=United+States` stays fixed here regardless of `country` for
    # now - gates.is_located_or_remote_in() downstream still correctly
    # rejects non-matching results for a non-US profile, this would just be
    # a server-side efficiency improvement for one, left for when a non-US
    # field actually needs it rather than guessed at here.
    postings: list[RawPosting] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"https://www.dice.com/jobs?q={quote(field.query_term)}&location=United+States&page={page}"
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

    relevant = [p for p in postings if gates.is_field_relevant(p, field)]
    with ThreadPoolExecutor(max_workers=DESCRIPTION_WORKERS) as pool:
        descriptions = pool.map(_fetch_description, [p.url for p in relevant])
    for posting, description in zip(relevant, descriptions):
        posting.description = description

    return postings
