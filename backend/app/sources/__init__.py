"""Source adapters. Each module exposes `fetch(query: str) -> list[RawPosting]`.

Add a new source by adding a module here and registering it in SOURCES below.
"""
from __future__ import annotations

from ..models import RawPosting
from . import dice_source, jobspy_source

SOURCES: dict[str, callable] = {
    "linkedin": jobspy_source.fetch_linkedin,
    "indeed": jobspy_source.fetch_indeed,
    "zip_recruiter": jobspy_source.fetch_zip_recruiter,
    "glassdoor": jobspy_source.fetch_glassdoor,
    "google": jobspy_source.fetch_google,
    "dice": dice_source.fetch_dice,
}

# Investigated and deliberately NOT integrated - see docs/ARCHITECTURE.md
# "Sources considered and rejected":
#   - jobright: no public API, requires an account, app/AI-matching platform
#     with no plain search page to scrape.
#   - jobgether: Cloudflare-protected (job detail pages return HTTP 403 to
#     plain requests); would need real browser automation to bypass reliably,
#     which is a different tier of effort/risk than the other sources here.


def fetch_all(source_names: list[str], query: str) -> list[RawPosting]:
    results: list[RawPosting] = []
    for name in source_names:
        fn = SOURCES.get(name)
        if fn is None:
            continue
        try:
            results.extend(fn(query))
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the fetch
            print(f"[sources] {name} failed: {exc}")
    return results
