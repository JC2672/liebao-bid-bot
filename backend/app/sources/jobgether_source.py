"""Jobgether adapter - real browser required, but NOT a login wall.

Plain HTTP requests get a 403 from Cloudflare on this site (verified: both
the search page and job-detail pages), but a real browser (even headless,
no login) sails through and search actually filters server-side once hit via
the site's own search box flow: /search-offers?keyword=<query> (NOT
/remote-jobs?keyword=<query>, which silently ignores the param - verified
interactively). So this uses Playwright to render the page and read the DOM,
no credentials involved.

No dedicated selectors/data-testids exist here (Astro site, utility-class
markup), so job cards are found structurally: walk up from every job-title
link (href^="/offer/") to the nearest ancestor that also contains a company
link (href^="/remote-jobs/company-") and, alongside it, a location link
(href^="/remote-jobs/<region>", the one link in that group that isn't the
company link). This is more fragile than a data-testid selector (Dice) but
is the only thing anchored to the site at all - it will need attention if
Jobgether restructures this markup.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from ..models import FieldConfig, RawPosting
from ._dates import parse_relative_date

SEARCH_URL = "https://jobgether.com/search-offers"
MAX_RESULTS = 100

_EXTRACT_JS = """
() => {
  // Company link and location link live under different ancestors of the
  // title link (siblings a couple of levels up, not nested inside each
  // other), so this climbs until BOTH are found rather than stopping the
  // moment the nearer one (company) turns up.
  const results = [];
  const seen = new Set();
  document.querySelectorAll('a[href^="/offer/"]').forEach(titleLink => {
    const href = titleLink.getAttribute('href');
    if (seen.has(href)) return;
    let container = titleLink.closest('div');
    let company = null, location = null;
    for (let i = 0; i < 10 && container; i++) {
      if (!company) {
        const c = container.querySelector('a[href^="/remote-jobs/company-"]');
        if (c) company = c.textContent.trim();
      }
      if (!location) {
        const l = [...container.querySelectorAll('a[href^="/remote-jobs/"]')]
          .find(a => !a.getAttribute('href').startsWith('/remote-jobs/company-'));
        if (l) location = l.textContent.trim();
      }
      if (company && location) break;
      container = container.parentElement;
    }
    if (company) {
      results.push({
        title: titleLink.textContent.trim(),
        url: href,
        company,
        location: location || '',
        posted: titleLink.nextElementSibling ? titleLink.nextElementSibling.textContent.trim() : '',
      });
      seen.add(href);
    }
  });
  return results;
}
"""


def _normalize_location(location: str) -> str:
    """'Remote from Mexico' -> 'Remote - Mexico', matching gates.py's convention.
    'Anywhere' (worldwide, no country restriction) becomes bare 'Remote' - a
    trailing '- Anywhere' would otherwise read as a non-US-scoped remote job
    to gates.py's REMOTE_NON_US_RE and get wrongly rejected."""
    loc = location.strip()
    if not loc:
        return "Remote"
    if loc.lower().startswith("remote from "):
        region = loc[len("Remote from "):].strip()
        if region.lower() in ("united states", "usa", "us"):
            return "Remote - United States"
        if region.lower() == "anywhere":
            return "Remote"
        return f"Remote - {region}"
    return f"Remote - {loc}"


def fetch_jobgether(field: FieldConfig, country: str, posted_within_days: int = 7) -> list[RawPosting]:  # noqa: ARG001 - no server-side date filter found on this endpoint
    postings: list[RawPosting] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ))
            page.goto(f"{SEARCH_URL}?keyword={field.query_term}", wait_until="networkidle", timeout=30000)
            page.wait_for_selector('a[href^="/offer/"]', timeout=15000)
            cards = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()

    for card in cards[:MAX_RESULTS]:
        postings.append(RawPosting(
            source="jobgether",
            external_id=card["url"].strip("/").split("/")[-1],
            url=f"https://jobgether.com{card['url']}",
            company=card["company"],
            title=card["title"],
            location=_normalize_location(card["location"]),
            description="",
            posted_at=parse_relative_date(card["posted"]) if card.get("posted") else None,
        ))
    return postings
