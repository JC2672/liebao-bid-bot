"""Talent.com adapter - real browser required, no login involved.

No official free API (only paid third-party scrapers exist). Directly
inspected instead of assumed: the search page itself loads fine with no
Cloudflare block, but its visible job cards are populated by a client-side
Next.js RSC request (a POST back to the same URL, streamed React payload) -
not present in the initial HTML (only a bare SEO ItemList of URLs, no
title/company/location), and not a stable plain-JSON API worth reverse-
engineering. Playwright reads the fully rendered DOM instead, same approach
as Jobgether. Pagination is a JS "Next page" button, not a URL param, so
this only reads the first page (~20 results) - the same tradeoff already
accepted for Jobright.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from ..models import RawPosting
from ._dates import parse_relative_date

SEARCH_URL = "https://www.talent.com/jobs"
MAX_RESULTS = 30

_EXTRACT_JS = """
() => {
  const results = [];
  document.querySelectorAll('article').forEach(article => {
    const titleEl = article.querySelector('h2');
    const link = article.querySelector('a[href^="/view?id="]');
    if (!titleEl || !link) return;
    const infoBlock = titleEl.parentElement;
    let infoText = '';
    if (infoBlock) {
      infoText = infoBlock.textContent.replace(titleEl.textContent, '').trim();
    }
    const [company, location] = infoText.split('\\u2022').map(s => (s || '').trim());
    const timeEl = article.querySelector('time');
    results.push({
      title: titleEl.textContent.trim(),
      url: link.getAttribute('href'),
      company: company || '',
      location: location || '',
      posted: timeEl ? timeEl.textContent.trim() : '',
    });
  });
  return results;
}
"""


def fetch_talent(query: str) -> list[RawPosting]:
    postings: list[RawPosting] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ))
            # "networkidle" times out here - the page has hanging third-party
            # tracker/font requests that never settle - so wait on the real
            # content selector instead.
            page.goto(
                f"{SEARCH_URL}?k={query}&l=United+States",
                wait_until="domcontentloaded", timeout=30000,
            )
            page.wait_for_selector("article", timeout=20000)
            cards = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()

    for card in cards[:MAX_RESULTS]:
        posted_text = card["posted"].replace("Last updated:", "").strip()
        postings.append(RawPosting(
            source="talent",
            external_id=card["url"].split("id=")[-1],
            url=f"https://www.talent.com{card['url']}",
            company=card["company"],
            title=card["title"],
            location=card["location"],
            description="",
            posted_at=parse_relative_date(posted_text) if posted_text else None,
        ))
    return postings
