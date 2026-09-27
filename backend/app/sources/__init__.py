"""Source adapters. Each module exposes `fetch(query: str) -> list[RawPosting]`.

Add a new source by adding a module here and registering it in SOURCES below.
"""
from __future__ import annotations

from ..models import RawPosting
from . import jobspy_source

SOURCES: dict[str, callable] = {
    "linkedin": jobspy_source.fetch_linkedin,
    "indeed": jobspy_source.fetch_indeed,
    "zip_recruiter": jobspy_source.fetch_zip_recruiter,
    "glassdoor": jobspy_source.fetch_glassdoor,
    "google": jobspy_source.fetch_google,
}


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
