"""Google Sheets access via a Google Apps Script Web App bound to the
profile's own Sheet - not a service account.

Why: a service account needs a Google Cloud project, an IAM key file
(`service-account.json`) to protect, and sharing the Sheet with a
machine-generated email - real setup friction for what this project is (a
single-user local tool). An Apps Script Web App needs none of that: open
the Sheet, Extensions > Apps Script, paste the script kept at
`docs/apps-script.gs`, Deploy > New deployment > Web app, and put the
resulting URL (plus the shared secret set inside that script) into the
profile. No Cloud project, no key file.

The real tradeoff, worth being explicit about: a Web App deployed as
"Execute as: Me / Anyone with the link" isn't authenticated by Google at
all - anyone who obtains the URL could call it. `sheet_secret` closes that
gap: every request carries it, and the deployed script rejects anything
that doesn't match before touching the sheet. Treat both the URL and the
secret as sensitive - they're stored in each profile's profile.json, which
lives on disk right alongside everything else (see profiles.py) and is not
meant to be shared or committed to git in a public state.

A profile's own tab is auto-created (with the header row) by the script
itself on first use, matching what `gspread`'s `add_worksheet` used to do
here directly.
"""
from __future__ import annotations

import time

import requests

TIMEOUT = 20  # Apps Script Web Apps have a real cold-start latency the first time they're hit
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.5

HEADER = ["Date", "Company", "Title", "Source", "Job URL", "Stage"]


def _call(webapp_url: str, secret: str, **body) -> dict:
    if not webapp_url:
        raise RuntimeError(
            "This profile has no Sheet Web App URL configured yet - see "
            "docs/apps-script.gs for how to set one up."
        )

    # Retried because this specific failure mode is transient, not a real
    # rejection - confirmed live: two profiles sharing one Sheet's Web App
    # deployment (same URL/secret, different tabs) hit Google's own
    # concurrent-execution limit for that script when one request landed
    # while another was still running, and got back an HTML "try again"
    # interstitial (status 200, not JSON) instead of ever reaching our
    # script. Retrying the exact same request a moment later succeeded
    # with no code or config change at all. A genuine application-level
    # rejection (bad secret, a real `error` field) is NOT retried below -
    # that will never succeed no matter how many times it's sent.
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(webapp_url, json={"secret": secret, **body}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_exc = RuntimeError(f"Could not reach the Sheet's Apps Script Web App: {exc}")
        else:
            try:
                data = resp.json()
            except ValueError:
                last_exc = RuntimeError(
                    f"The Sheet's Apps Script Web App returned something unexpected "
                    f"(HTTP {resp.status_code}): {resp.text[:200]}"
                )
            else:
                if data.get("error"):
                    raise RuntimeError(f"The Sheet's Apps Script Web App rejected the request: {data['error']}")
                return data

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    raise last_exc  # noqa: RSE102 - always set: the loop only exits here after every attempt landed in an except/else-failure branch


def get_applied_urls(webapp_url: str, secret: str, tab_name: str) -> set[str]:
    """Used for dedupe on import: URLs already applied-to for this profile."""
    data = _call(webapp_url, secret, action="get_urls", tab=tab_name)
    return {u.strip() for u in data.get("urls", []) if u}


def get_applied_rows_for_companies(
    webapp_url: str, secret: str, tab_name: str, companies: set[str] | list[str]
) -> dict[str, list[dict]]:
    """Used to flag (not block - see routers/queue.py's company-dupe flag on
    import) a newly-queued row whose company already shows up in this
    profile's Applied sheet - keyed by lowercased/stripped company name so
    "Acme Inc" and "acme inc " group together, each value the list of past
    applications at that company (title/date/stage), for the Queue table's
    hover detail rather than just a yes/no.

    `companies` scopes the lookup to just the companies actually in the
    current import batch - the Apps Script filters server-side, so this
    never pulls the whole Applied log back just to answer "any of these
    show up before?" for a handful of rows."""
    if not companies:
        return {}
    data = _call(webapp_url, secret, action="get_applied_rows_for_companies", tab=tab_name, companies=list(companies))
    by_company: dict[str, list[dict]] = {}
    for row in data.get("rows", []):
        company = str(row.get("company") or "").strip()
        if not company:
            continue
        by_company.setdefault(company.lower(), []).append({
            "title": str(row.get("title") or ""),
            "date": str(row.get("date") or ""),
            "stage": str(row.get("stage") or ""),
        })
    return by_company


def append_applied_row(webapp_url: str, secret: str, tab_name: str, *, date: str, company: str,
                        title: str, source: str, url: str, stage: str = "Applied") -> None:
    _call(webapp_url, secret, action="append", tab=tab_name,
          date=date, company=company, title=title, source=source, url=url, stage=stage)
