"""Talent.com adapter - real browser required, no login involved.

No official free API (only paid third-party scrapers exist). Directly
inspected instead of assumed: the search page itself loads fine with no
Cloudflare block, but its visible job cards are populated by a client-side
Next.js RSC request (a POST back to the same URL, streamed React payload) -
not present in the initial HTML (only a bare SEO ItemList of URLs, no
title/company/location), and not a stable plain-JSON API worth reverse-
engineering. Playwright reads the fully rendered DOM instead, same approach
as Jobgether.

Pagination is a "Next page" button (no URL param), but since we already have
a real browser open for this source, we just click it - verified live that
this genuinely advances the result set (the first card's URL changes each
click). Contrast with Jobright, which has no browser open at all (plain
`requests` reading embedded JSON) and, more importantly, has no pagination
control whatsoever for anonymous visitors to click - confirmed by opening it
in a real browser and finding no "Next"/"Load more"/infinite-scroll of any
kind, so that one stays capped at one page regardless.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from ..models import RawPosting
from ._dates import parse_relative_date

SEARCH_URL = "https://www.talent.com/jobs"
MAX_PAGES = 4  # ~20 results/page

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


def _card_to_posting(card: dict) -> RawPosting:
    posted_text = card["posted"].replace("Last updated:", "").strip()
    return RawPosting(
        source="talent",
        external_id=card["url"].split("id=")[-1],
        url=f"https://www.talent.com{card['url']}",
        company=card["company"],
        title=card["title"],
        location=card["location"],
        description="",
        posted_at=parse_relative_date(posted_text) if posted_text else None,
    )


def fetch_talent(query: str) -> list[RawPosting]:
    postings: list[RawPosting] = []
    seen_urls: set[str] = set()

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

            for _ in range(MAX_PAGES):
                cards = page.evaluate(_EXTRACT_JS)
                new_cards = [c for c in cards if c["url"] not in seen_urls]
                if not new_cards:
                    break  # same page again - button didn't advance, stop
                for card in new_cards:
                    seen_urls.add(card["url"])
                    postings.append(_card_to_posting(card))

                first_url_before = cards[0]["url"] if cards else None
                try:
                    page.get_by_role("button", name="Next page").click(timeout=15000)
                except Exception:  # noqa: BLE001 - last page: button missing/disabled
                    break
                # Wait for the RSC-updated content to actually replace the
                # old cards rather than trusting a fixed delay.
                try:
                    page.wait_for_function(
                        """(prevFirst) => {
                            const a = document.querySelector('a[href^="/view?id="]');
                            return a && a.getAttribute('href') !== prevFirst;
                        }""",
                        arg=first_url_before, timeout=8000,
                    )
                except Exception:  # noqa: BLE001 - content didn't change - stop
                    break
        finally:
            browser.close()

    return postings
