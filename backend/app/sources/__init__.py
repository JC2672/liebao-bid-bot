"""Source adapters. Each module exposes
`fetch(field: FieldConfig, country: str, posted_within_days: int) -> list[RawPosting]`.
`field` carries the active Profile's query term/title list/relevance
keywords (see fields.py, gates.py) - most sources just read
`field.query_term` where they used to read a free-text `query` parameter;
a few (Jobright, Indeed, Built In, Jobspresso) fan out over
`field.title_list` instead, since a bare query term is a known trap on
those specifically. Most sources ignore `posted_within_days` (gates.py's
own posted-within-N-days gate filters client-side afterward regardless) -
it's there for the sources whose own API can filter server-side, which
matters a lot when a source sorts by relevance rather than by date:
pulling a fixed-size page of "most relevant" results and then discarding
old ones client-side can miss genuinely recent postings entirely if they
don't happen to also rank high on relevance. Jobright is a confirmed real
case of this - see its module's docstring.

Add a new source by adding a module here and registering it in SOURCES below.
"""
from __future__ import annotations

from . import (
    arbeitnow_source,
    ats_boards_source,
    builtin_source,
    dice_source,
    himalayas_source,
    jobgether_source,
    jobicy_source,
    jobright_source,
    jobspresso_source,
    jobspy_source,
    monster_source,
    remoteok_source,
    remotive_source,
    talent_source,
    weworkremotely_source,
    workingnomads_source,
)

SOURCES: dict[str, callable] = {
    "linkedin": jobspy_source.fetch_linkedin,
    "indeed": jobspy_source.fetch_indeed,
    "dice": dice_source.fetch_dice,
    "remotive": remotive_source.fetch_remotive,
    "remoteok": remoteok_source.fetch_remoteok,
    "weworkremotely": weworkremotely_source.fetch_weworkremotely,
    "jobgether": jobgether_source.fetch_jobgether,
    "jobright": jobright_source.fetch_jobright,
    "himalayas": himalayas_source.fetch_himalayas,
    "jobicy": jobicy_source.fetch_jobicy,
    "arbeitnow": arbeitnow_source.fetch_arbeitnow,
    "workingnomads": workingnomads_source.fetch_workingnomads,
    "greenhouse": ats_boards_source.fetch_greenhouse,
    "lever": ats_boards_source.fetch_lever,
    "ashby": ats_boards_source.fetch_ashby,
    "talent": talent_source.fetch_talent,
    "builtin": builtin_source.fetch_builtin,
    "jobspresso": jobspresso_source.fetch_jobspresso,
    "monster": monster_source.fetch_monster,
}

# The Muse: investigated and NOT integrated. Its public API has no free-text
# search and no category matching "Salesforce" (or CRM/tech at all usefully);
# it's 400k+ jobs total, so scanning enough pages to find relevant postings
# by chance isn't practical the way it is for We Work Remotely/Arbeitnow/
# Working Nomads (each only tens-to-low-hundreds of postings total).

# Obra: investigated directly and NOT integrated - and not revisitable
# without real credentials. Its web app is gated behind Firebase App Check,
# a purpose-built anti-automation service (distinct from incidental
# Cloudflare bot-protection seen elsewhere): a single real-browser visit hit
# a 403 that self-throttles further attempts for 24 hours. This is a
# deliberate anti-scraping measure, not a fetchable source.

# No source currently needs real login credentials - both Jobright and
# Jobgether looked account-gated/blocked from web search and a plain curl
# respectively, but direct inspection (playwright-cli) showed anonymous
# access works for both once hit the right way. See each module's docstring.
# If a genuinely login-gated source comes up later, the plan is a Playwright
# persistent-context profile per source (login once in a visible browser,
# reuse the saved storage_state for headless fetches) - not built yet since
# nothing has needed it so far.

