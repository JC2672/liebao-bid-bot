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

import requests

TIMEOUT = 20  # Apps Script Web Apps have a real cold-start latency the first time they're hit

HEADER = ["Date", "Company", "Title", "Source", "Job URL"]


def _call(webapp_url: str, secret: str, **body) -> dict:
    if not webapp_url:
        raise RuntimeError(
            "This profile has no Sheet Web App URL configured yet - see "
            "docs/apps-script.gs for how to set one up."
        )
    try:
        resp = requests.post(webapp_url, json={"secret": secret, **body}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the Sheet's Apps Script Web App: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"The Sheet's Apps Script Web App returned something unexpected "
            f"(HTTP {resp.status_code}): {resp.text[:200]}"
        ) from exc

    if data.get("error"):
        raise RuntimeError(f"The Sheet's Apps Script Web App rejected the request: {data['error']}")
    return data


def get_applied_urls(webapp_url: str, secret: str, tab_name: str) -> set[str]:
    """Used for dedupe on import: URLs already applied-to for this profile."""
    data = _call(webapp_url, secret, action="get_urls", tab=tab_name)
    return {u.strip() for u in data.get("urls", []) if u}


def append_applied_row(webapp_url: str, secret: str, tab_name: str, *, date: str, company: str,
                        title: str, source: str, url: str) -> None:
    _call(webapp_url, secret, action="append", tab=tab_name,
          date=date, company=company, title=title, source=source, url=url)
