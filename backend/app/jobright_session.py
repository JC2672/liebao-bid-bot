"""Jobright login session, held in a dedicated Playwright-managed Chromium
profile - not the user's own daily Chrome (that would need a companion
browser extension, deferred; see docs/ARCHITECTURE.md).

Flow:
  1. Frontend checks GET /sources/jobright/status.
  2. If not logged in, POST /sources/jobright/login/start opens a VISIBLE
     Chromium window on Jobright's login page and returns immediately - the
     browser stays open (held in _active_login) across requests.
  3. User signs in by hand in that window; the frontend then calls
     POST /sources/jobright/login/finish, which saves the session
     (Playwright storage_state: cookies) to disk and closes the window.
  4. jobright_source.py loads the saved cookies and attaches them as a plain
     Cookie header on ordinary `requests` calls to Jobright's real internal
     API - no browser needed for the fetch itself, only for the one-time
     login. Confirmed live: that API returns a clean, unambiguous signal for
     an invalid/missing session (HTTP 401, {"success": false, "errorCode":
     41001, "errorMsg": "Cookie not found"}), which is what check_session()
     relies on.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "browser-sessions" / "jobright"
STATE_PATH = SESSION_DIR / "storage_state.json"

API_ORIGIN = "https://jobright.ai"
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "x-client-type": "web",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# Holds the live Playwright objects for an in-progress interactive login,
# across the separate start/finish HTTP requests. Empty when no login is
# in progress. Single-user local app, so a module-level dict is fine.
_active_login: dict = {}


def get_cookie_header() -> str:
    """Cookie header string for jobright.ai, or "" if never logged in."""
    if not STATE_PATH.exists():
        return ""
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    cookies = state.get("cookies", [])
    pairs = [f"{c['name']}={c['value']}" for c in cookies if "jobright.ai" in c.get("domain", "")]
    return "; ".join(pairs)


def check_session() -> bool:
    """Makes one cheap real request to confirm the saved session still
    works, rather than trusting that a storage_state file merely exists."""
    cookie = get_cookie_header()
    if not cookie:
        return False
    headers = {**DEFAULT_HEADERS, "cookie": cookie}
    body = {
        "searchType": "job_title", "value": "Salesforce",
        "jobTaxonomyList": [{"taxonomyId": "00-00-00", "title": "Salesforce"}],
        "country": "US", "jobTypes": [], "seniority": [], "workModel": [],
        "locations": [], "companies": [], "isH1BOnly": False, "companyCategory": None,
        "annualSalaryMinimum": None, "roleType": None, "companyStages": None, "skills": [],
        "excludedCompanies": [], "excludedSkills": None, "excludeStaffingAgency": False,
        "minYearsOfExperienceRange": None, "excludeCompanyCategory": [],
        "excludeSecurityClearance": False, "excludeUsCitizen": False,
        "daysAgo": None, "refresh": True, "position": 0, "sortCondition": 0,
    }
    try:
        resp = requests.post(
            f"{API_ORIGIN}/swan/recommend/search",
            params={"searchType": "job_title", "refresh": "true", "count": 1, "position": 0, "sortCondition": 0},
            headers=headers, json=body, timeout=15,
        )
        return resp.status_code == 200 and resp.json().get("success") is True
    except (requests.RequestException, ValueError):
        return False


def login_in_progress() -> bool:
    return bool(_active_login)


def start_login() -> None:
    if _active_login:
        return
    from playwright.sync_api import sync_playwright  # local import: only needed for login

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto("https://jobright.ai/jobs/search", wait_until="domcontentloaded", timeout=60000)
    _active_login.update(playwright=pw, browser=browser, context=context)


def finish_login() -> bool:
    """Saves the session from the still-open login window. Returns whether
    it looks like a real logged-in session was actually captured."""
    if not _active_login:
        return False
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _active_login["context"].storage_state(path=str(STATE_PATH))
    finally:
        _close_active_login()
    return check_session()


def cancel_login() -> None:
    _close_active_login()


def _close_active_login() -> None:
    if not _active_login:
        return
    try:
        _active_login["browser"].close()
    except Exception:  # noqa: BLE001 - user may have already closed the window by hand
        pass
    try:
        _active_login["playwright"].stop()
    except Exception:  # noqa: BLE001
        pass
    _active_login.clear()
