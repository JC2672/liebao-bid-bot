"""Source adapters. Each module exposes `fetch(query: str) -> list[RawPosting]`.

Add a new source by adding a module here and registering it in SOURCES below.
"""
from __future__ import annotations

from ..models import RawPosting
from . import (
    dice_source,
    jobgether_source,
    jobright_source,
    jobspy_source,
    remoteok_source,
    remotive_source,
    weworkremotely_source,
)

SOURCES: dict[str, callable] = {
    "linkedin": jobspy_source.fetch_linkedin,
    "indeed": jobspy_source.fetch_indeed,
    "zip_recruiter": jobspy_source.fetch_zip_recruiter,
    "glassdoor": jobspy_source.fetch_glassdoor,
    "google": jobspy_source.fetch_google,
    "dice": dice_source.fetch_dice,
    "remotive": remotive_source.fetch_remotive,
    "remoteok": remoteok_source.fetch_remoteok,
    "weworkremotely": weworkremotely_source.fetch_weworkremotely,
    "jobgether": jobgether_source.fetch_jobgether,
    "jobright": jobright_source.fetch_jobright,
}

# No source currently needs real login credentials - both Jobright and
# Jobgether looked account-gated/blocked from web search and a plain curl
# respectively, but direct inspection (playwright-cli) showed anonymous
# access works for both once hit the right way. See each module's docstring.
# If a genuinely login-gated source comes up later, the plan is a Playwright
# persistent-context profile per source (login once in a visible browser,
# reuse the saved storage_state for headless fetches) - not built yet since
# nothing has needed it so far.


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
