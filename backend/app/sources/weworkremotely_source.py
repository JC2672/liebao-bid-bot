"""We Work Remotely adapter - public RSS feed, no login, no API key.

The feed has no search/keyword param, so this pulls the combined "all jobs"
feed (most recent ~100 postings across every category) and lets gates.py do
the Salesforce-relevance filtering, same pattern as the Dice adapter.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

from ..models import FieldConfig, RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FEED_URL = "https://weworkremotely.com/remote-jobs.rss"


def _normalize_region(region: str) -> str:
    """Map WWR's free-text region into a string gates.py's location regexes
    already understand ("Remote", "Remote - United States", "Remote - X")."""
    r = region.strip().lower()
    if not r or "anywhere in the world" in r or "worldwide" in r:
        return "Remote"
    if "usa" in r or "us only" in r or "united states" in r:
        return "Remote - United States"
    if "north america" in r:
        return "Remote"  # ambiguous (includes Canada) - pass through as unscoped remote
    return f"Remote - {region.strip()}"


def _clean_description(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)


def fetch_weworkremotely(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side search or date filter
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    postings: list[RawPosting] = []
    for item in root.iterfind(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        company, _, job_title = raw_title.partition(": ")
        if not job_title:
            company, job_title = "", raw_title

        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        region = item.findtext("region") or ""
        description_html = item.findtext("description") or ""

        posted_at: datetime | None = None
        pub_date = item.findtext("pubDate")
        if pub_date:
            try:
                posted_at = parsedate_to_datetime(pub_date)
            except (TypeError, ValueError):
                posted_at = None

        postings.append(RawPosting(
            source="weworkremotely",
            external_id=re.sub(r"[^a-zA-Z0-9]+", "-", guid)[-120:],
            url=link,
            company=company.strip(),
            title=job_title.strip(),
            location=_normalize_region(region),
            description=_clean_description(description_html),
            posted_at=posted_at,
        ))
    return postings
