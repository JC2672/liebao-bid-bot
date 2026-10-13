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

Full job description IS fetched now - confirmed live this was a real gap,
not an intentional omission: the search page's cards never embedded one
(every row came through with `description=""`), and the real text only
lives on each job's own detail page, under an `<h2>Job description</h2>`
heading (same text-based lookup as the card extraction above, since this
site has no stable selectors to anchor to either). Fetched only for
postings that already pass the title-relevance gate, same reasoning as
Dice's own per-listing detail fetch - no point paying for a detail-page
load that's going to be discarded anyway. Can't be parallelized with
threads the way Dice's plain `requests` calls are (Playwright's sync API
isn't thread-safe across a single browser/page) - fetched sequentially,
reusing the one page already open in this module's browser context.
"""
from __future__ import annotations

from playwright.sync_api import Page, sync_playwright

from .. import gates
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


_DESCRIPTION_JS = """
() => {
  const h = [...document.querySelectorAll('h2')].find(e => e.textContent.trim() === 'Job description');
  return h && h.parentElement ? h.parentElement.innerText.trim() : '';
}
"""
_DESCRIPTION_LABEL = "Job description"


def _fetch_description(page: Page, url: str) -> str:
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        text = page.evaluate(_DESCRIPTION_JS)
    except Exception:  # noqa: BLE001 - a failed detail-page load just leaves this one row without a description
        return ""
    # The heading itself is the first line of parentElement.innerText -
    # dropped here in plain Python rather than via DOM text-matching
    # (confirmed live: comparing innerText against the heading's own
    # textContent didn't reliably match, likely a whitespace/line-break
    # difference between the two) so the stored description starts at the
    # real content, not a repeated label line.
    if text.startswith(_DESCRIPTION_LABEL):
        text = text[len(_DESCRIPTION_LABEL):]
    return text.strip()


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

            for posting in postings:
                if gates.is_field_relevant(posting, field):
                    posting.description = _fetch_description(page, posting.url)
        finally:
            browser.close()

    return postings
