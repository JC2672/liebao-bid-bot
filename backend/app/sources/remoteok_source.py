"""RemoteOK adapter - public JSON API, no login, no API key.

Note: plain `curl` on this machine hangs against remoteok.com (a Windows
schannel TLS-renegotiation quirk, not real bot-blocking) - `requests` (used
here, via urllib3/OpenSSL) has no such problem and was verified working.

RemoteOK's own terms ask that callers link back to remoteok.com, which this
project already does (the stored `url` is what "Open Post" opens).

Known gap: RemoteOK's `location` field is inconsistent - often a bare city
with no state/country ("Redwood City"), sometimes empty (implying worldwide).
Bare cities with no state/country will fail the US-location gate as a false
negative until that regex grows a city lookup - worth revisiting once real
fetch results are being reviewed (see docs/ARCHITECTURE.md gate tuning notes).
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import FieldConfig, RawPosting

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
API_URL = "https://remoteok.com/api"


def _request(tag: str) -> list[dict]:
    params = {"tags": tag} if tag else {}
    resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _matches_query(job: dict, words: list[str]) -> bool:
    text = f"{job.get('position', '')} {job.get('company', '')} {job.get('description', '')}".lower()
    return any(w in text for w in words)


def fetch_remoteok(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter on this endpoint
    # RemoteOK's `tags` param is an exact match against its own single-word
    # tag vocabulary (e.g. "salesforce"), not a free-text search - a phrase
    # like "Salesforce Administrator" matches no tag at all and silently
    # returns zero results. Try the first word as a tag (the common case:
    # "Salesforce", "Salesforce Developer", etc. all start with a real tag);
    # if that comes back empty, fall back to the site's general/latest feed
    # and filter it locally by whether any query-term word appears in the
    # title/company/description.
    words = [w for w in field.query_term.strip().lower().split() if w]
    data = _request(words[0]) if words else _request("")
    if len(data) <= 1 and words:  # only the legal-notice object came back
        data = [job for job in _request("") if _matches_query(job, words)]

    postings: list[RawPosting] = []
    for job in data:
        if "position" not in job:
            continue  # first element is a legal-notice object, not a job

        location = (job.get("location") or "").strip()
        posted_at: datetime | None = None
        if job.get("epoch"):
            posted_at = datetime.fromtimestamp(job["epoch"], tz=timezone.utc)

        postings.append(RawPosting(
            source="remoteok",
            external_id=str(job.get("id", job.get("slug", ""))),
            url=job.get("url", "").replace("remoteOK.com", "remoteok.com"),
            company=job.get("company", ""),
            title=job.get("position", ""),
            location=f"Remote - {location}" if location else "Remote",
            description=BeautifulSoup(job.get("description", ""), "html.parser").get_text("\n", strip=True),
            posted_at=posted_at,
        ))
    return postings
