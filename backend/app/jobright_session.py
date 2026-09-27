"""Jobright login session, held in the user's REAL browser - not a separate
automation profile (an earlier version of this used a dedicated Playwright-
managed Chromium window the user had to log into a second time; that was the
wrong shape for this and has been replaced).

Flow:
  1. The companion Chrome extension (extension/) reads the user's actual
     jobright.ai cookies from their own already-open Chrome via
     chrome.cookies, which only an extension can do - an ordinary web page
     can't read another origin's cookies itself.
  2. The extension POSTs those cookies to /sources/jobright/cookies here,
     which saves them and reports back whether they actually work.
  3. jobright_source.py loads the saved cookies and attaches them as a plain
     Cookie header on ordinary `requests` calls to Jobright's real internal
     API - no browser involved in the fetch itself, only in obtaining the
     cookies in the first place.

check_session() makes one cheap real request rather than trusting that a
saved file merely exists: confirmed live that Jobright's real API returns a
clean, unambiguous signal for an invalid/missing session (HTTP 401,
{"success": false, "errorCode": 41001, "errorMsg": "Cookie not found"}).
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "browser-sessions" / "jobright"
COOKIES_PATH = SESSION_DIR / "cookies.json"

API_ORIGIN = "https://jobright.ai"
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "x-client-type": "web",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def save_cookies(cookies: list[dict]) -> None:
    """`cookies`: [{"name": ..., "value": ..., "domain": ...}, ...], exactly
    the shape chrome.cookies.getAll() returns (extra fields are fine, only
    name/value/domain are read back)."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.write_text(json.dumps({"cookies": cookies}, indent=2), encoding="utf-8")


def get_cookie_header() -> str:
    """Cookie header string for jobright.ai, or "" if no session saved yet."""
    if not COOKIES_PATH.exists():
        return ""
    try:
        state = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    cookies = state.get("cookies", [])
    pairs = [f"{c['name']}={c['value']}" for c in cookies if "jobright.ai" in c.get("domain", "")]
    return "; ".join(pairs)


def check_session() -> bool:
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
