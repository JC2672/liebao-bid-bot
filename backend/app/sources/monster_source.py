"""Monster adapter - Playwright, best-effort, following the same approach a
sibling local project already uses for this source.

Monster is behind DataDome, a commercial anti-bot service. Confirmed live
(2026-09-29), working through this with the user: a real, logged-in
browser's own session passes with zero challenge at all (the block is
specifically an automation-fingerprint check - CDP/`navigator.webdriver`
etc - not an IP/network block), but replaying that same real session's
cookies through a *different* HTTP client (our own backend's `requests`)
still gets a flat 403 with a `captcha-delivery.com` challenge, on both the
search page and the real `search-jobs` API - DataDome ties validity to the
connecting client's TLS/JA3 fingerprint (it explicitly issues a `mn_ja3`
cookie), not just cookie possession. That rules out a Jobright-style
cookie relay here: our backend presenting your real cookies isn't the same
client that earned them.

Plain Playwright with `--disable-blink-features=AutomationControlled` plus
a realistic UA/locale/viewport gets past the page-level check (confirmed
live - no more CAPTCHA page shell), but the underlying `search-jobs` API
call is still 403'd every time (confirmed live via network tracing) - the
page just renders its own "no jobs found" fallback UI when that happens,
which looks identical to a genuine empty search from the DOM alone. That
means the sibling project's own detection heuristic (body text under 40
chars = blocked) has a blind spot here: this failure mode renders a
normal-sized page (1300+ characters) that's actually empty boilerplate,
not real results. Kept anyway, since the practical effect is the same
either way - the title-relevance filter below finds zero stub links and
returns `[]` cleanly, no crash - matching the sibling project's own
documented experience of this source: real results only on the rare run
DataDome doesn't intervene, nothing (silently, not an error) the rest of
the time. A deliberate best-effort inclusion, not a reliable one.

Uses a single "Salesforce" query (not the SALESFORCE_TITLES fan-out other
sources use) - firing 32 seeded-title searches through real Playwright
navigations against a source that's usually going to get blocked anyway
isn't worth the time or the extra automated-traffic footprint. Title
relevance (gates.py's own check) filters candidates before spending a
detail-page visit on them.
"""
from __future__ import annotations

import re
from datetime import datetime

from playwright.sync_api import sync_playwright

from ..gates import _is_salesforce_relevant
from ..models import RawPosting

SEARCH_URL = "https://www.monster.com/jobs/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
MAX_PAGES = 3
MIN_BODY_LEN = 40  # below this, treat the page as blocked/empty - same threshold the sibling project uses

_STUB_JS = """
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/job-openings/"], a[href*="jobid="]')) {
    const href = (a.href || '').split('#')[0];
    if (!href || seen.has(href)) continue;
    seen.add(href);
    out.push({ url: href, title: (a.textContent || '').replace(/\\s+/g, ' ').trim() });
  }
  return out;
}
"""

_DETAIL_JS = """
() => {
  const text = (el) => (el ? (el.textContent || '').replace(/\\s+/g, ' ').trim() : '');
  let ld = null;
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const parsed = JSON.parse(s.textContent || '');
      const nodes = Array.isArray(parsed) ? parsed : [parsed];
      for (const n of nodes) {
        if (n && (n['@type'] === 'JobPosting' || n.title)) { ld = n; break; }
      }
    } catch {}
    if (ld) break;
  }
  const body = document.body ? document.body.innerText || '' : '';
  const head = body.slice(0, 2000);
  let work = '';
  if (/\\bhybrid\\b/i.test(head)) work = 'Hybrid';
  else if (/\\bon[-\\s]?site\\b/i.test(head) && !/\\bremote\\b/i.test(head)) work = 'Onsite';
  else if (/\\bremote\\b/i.test(head)) work = 'Remote';
  else if (ld && ld.jobLocationType === 'TELECOMMUTE') work = 'Remote';
  return {
    title: text(document.querySelector('h1')) || (ld && ld.title) || '',
    company: (ld && (ld.hiringOrganization && ld.hiringOrganization.name || ld.hiringOrganization)) || '',
    description: (ld && ld.description) || text(document.querySelector('[class*="description"]')) || body.slice(0, 15000),
    date_posted: (ld && ld.datePosted) || '',
    work_arrangement: work,
  };
}
"""

_ID_RE = re.compile(r"--([a-f0-9-]{20,})", re.IGNORECASE)
_JOBID_RE = re.compile(r"jobid=([^&]+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_id(url: str) -> str:
    m = _ID_RE.search(url) or _JOBID_RE.search(url)
    return m.group(1) if m else url


def _parse_iso_date(text: str) -> datetime | None:
    """JSON-LD's `datePosted` is real ISO 8601 (e.g. "2026-09-20T00:00:00Z"),
    not the "X days ago" text other sources expose - _dates.py's
    parse_relative_date doesn't apply here."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _location_for(work_arrangement: str) -> str:
    # Search was scoped to where=Remote, so default to bare "Remote" (gates.py
    # treats that as US-ambiguous-but-accepted) unless the detail page itself
    # says otherwise.
    if work_arrangement == "Hybrid":
        return "Hybrid"
    if work_arrangement == "Onsite":
        return "Onsite"
    return "Remote"


def fetch_monster(query: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - single fixed query, see module docstring
    stubs: list[dict] = []
    seen_urls: set[str] = set()
    blocked = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                extra_http_headers={"accept-language": "en-US,en;q=0.9"},
            )
            page = context.new_page()

            for p in range(1, MAX_PAGES + 1):
                page.goto(
                    f"{SEARCH_URL}?q=Salesforce&where=Remote&page={p}&so=m.h.sh",
                    wait_until="domcontentloaded", timeout=60000,
                )
                page.wait_for_timeout(5000)

                body_len = page.evaluate("() => (document.body?.innerText || '').length")
                if body_len < MIN_BODY_LEN:
                    print(f"[monster] blocked/empty page (bodyLen={body_len}) - skipping this run")
                    blocked = True
                    break

                page_stubs = page.evaluate(_STUB_JS)
                if not page_stubs:
                    break

                new_on_page = 0
                for stub in page_stubs:
                    if stub["url"] in seen_urls:
                        continue
                    seen_urls.add(stub["url"])
                    if stub["title"] and not _is_salesforce_relevant(
                        RawPosting(source="monster", external_id="", url="", company="",
                                    title=stub["title"], location="", description="")
                    ):
                        continue
                    stubs.append(stub)
                    new_on_page += 1
                if new_on_page == 0:
                    break

            postings: list[RawPosting] = []
            for stub in stubs:
                try:
                    page.goto(stub["url"], wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(1200)
                    data = page.evaluate(_DETAIL_JS)
                except Exception as exc:  # noqa: BLE001 - one detail page failing shouldn't kill the rest
                    print(f"[monster] detail fetch failed for {stub['url']!r}: {exc}")
                    continue

                description = _TAG_RE.sub(" ", str(data.get("description") or "")).strip()
                postings.append(RawPosting(
                    source="monster",
                    external_id=_extract_id(stub["url"]),
                    url=stub["url"].split("?")[0],
                    company=str(data.get("company") or "").strip(),
                    title=data.get("title") or stub["title"],
                    location=_location_for(data.get("work_arrangement") or ""),
                    description=description,
                    posted_at=_parse_iso_date(str(data.get("date_posted") or "")),
                ))
        finally:
            browser.close()

    if blocked and not stubs:
        print("[monster] no results this run - blocked before finding any candidates")
    return postings
