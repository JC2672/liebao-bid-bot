"""Hard gates + soft flags applied to fetched postings.

Gates reject (with a stored reason, shown not discarded). Flags are informational
badges the UI shows on passing rows. See docs/ARCHITECTURE.md "Fetch: sources & gates".
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .models import GateResult, RawPosting

# --- Salesforce relevance -----------------------------------------------

SALESFORCE_ALLOW = re.compile(
    r"\b(salesforce|apex|visualforce|lwc|lightning\s+web\s+component|"
    r"soql|sosl|omnistudio|vlocity|mulesoft|cpq|pardot|marketing\s+cloud|"
    r"service\s+cloud|sales\s+cloud|experience\s+cloud|data\s+cloud|"
    r"health\s+cloud|revenue\s+cloud|financial\s+services\s+cloud|"
    r"agentforce|salesforce\s+admin|salesforce\s+developer|"
    r"salesforce\s+architect|salesforce\s+consultant)\b",
    re.IGNORECASE,
)

# Titles that mention Salesforce but aren't Salesforce technical roles
# (e.g. "Account Executive, Salesforce" = selling FOR Salesforce Inc.,
# "manage the sales force" style false positives).
SALESFORCE_TITLE_NEGATIVE = re.compile(
    r"\b(account\s+executive|account\s+manager|sales\s+representative|"
    r"sales\s+force\s+(effectiveness|management)|regional\s+sales)\b",
    re.IGNORECASE,
)


def _is_salesforce_relevant(posting: RawPosting) -> bool:
    # Title-only, not title+description: a passing tool mention buried in a
    # long description is not enough on its own - confirmed as a real,
    # common false-positive pattern live (Indeed): "Healthcare Sales
    # Director" passed because its JD said "...tracking in Salesforce",
    # despite the role having nothing to do with Salesforce development/
    # administration. Genuine Salesforce-ecosystem roles overwhelmingly say
    # so in the title itself (Salesforce Developer, Marketing Cloud
    # Developer, MuleSoft Developer, etc.) - every example the user asked
    # this project to target does. Some sources don't fetch full
    # descriptions at all (Dice, Jobgether, Talent.com), so this also makes
    # gating consistent across sources rather than accidentally stricter
    # for ones that happen to return rich description text.
    if not SALESFORCE_ALLOW.search(posting.title):
        return False
    if SALESFORCE_TITLE_NEGATIVE.search(posting.title):
        return False
    return True


# --- US / Remote location -------------------------------------------------

US_STATE_ABBR = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
US_LOCATION_RE = re.compile(
    rf"\b(united\s+states|usa|u\.s\.a?\.?)\b|,\s*(?:{US_STATE_ABBR})\b",
    re.IGNORECASE,
)
# Remote, but scoped to somewhere that is NOT the US -> reject.
REMOTE_NON_US_RE = re.compile(
    r"remote\s*[-–—(]\s*(?!us\b|u\.s\.?\b|usa\b|united\s+states\b)[a-z]",
    re.IGNORECASE,
)
REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)


def _is_us_or_us_remote(posting: RawPosting) -> bool:
    loc = posting.location or ""
    if REMOTE_NON_US_RE.search(loc):
        return False
    if US_LOCATION_RE.search(loc):
        return True
    if REMOTE_RE.search(loc) and not REMOTE_NON_US_RE.search(loc):
        # Bare "Remote" with no country qualifier: accept, but this is exactly
        # the ambiguous case worth a flag too (see _flags below).
        return True
    if posting.is_remote and not REMOTE_NON_US_RE.search(loc):
        return True
    return False


# --- Flags (informational, non-rejecting) --------------------------------

NO_SPONSORSHIP_RE = re.compile(
    r"\b(no\s+sponsorship|not\s+able\s+to\s+sponsor|us\s+citizens?\s+only|"
    r"must\s+be\s+a?\s*us\s+citizen|green\s+card\s+holders?\s+only)\b",
    re.IGNORECASE,
)
C2C_RE = re.compile(r"\bC2C\b|corp[-\s]?to[-\s]?corp", re.IGNORECASE)
W2_ONLY_RE = re.compile(r"\bW2\s+only\b|\bW-2\s+only\b", re.IGNORECASE)
AGENCY_RE = re.compile(
    r"\b(staffing|recruiting\s+agency|talent\s+acquisition\s+partner|client\s+of\s+ours)\b",
    re.IGNORECASE,
)


def _flags(posting: RawPosting) -> list[str]:
    text = f"{posting.title}\n{posting.location}\n{posting.description}"
    flags: list[str] = []
    if NO_SPONSORSHIP_RE.search(text):
        flags.append("no-sponsorship")
    if C2C_RE.search(text):
        flags.append("c2c")
    if W2_ONLY_RE.search(text):
        flags.append("w2-only")
    if AGENCY_RE.search(text):
        flags.append("agency")
    if HYBRID_RE.search(posting.location or ""):
        flags.append("hybrid")
    if REMOTE_RE.search(posting.location or "") and not US_LOCATION_RE.search(posting.location or ""):
        flags.append("remote-unscoped")  # "Remote" with no country stated
    return flags


# --- Posted-within-N-days -------------------------------------------------


def _within_days(posting: RawPosting, days: int) -> bool:
    if posting.posted_at is None:
        return True  # unknown date: don't reject on this alone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    posted = posting.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted >= cutoff


# --- Public entry point ---------------------------------------------------


def apply_gates(posting: RawPosting, posted_within_days: int = 7) -> GateResult:
    base = dict(
        source=posting.source,
        external_id=posting.external_id,
        url=posting.url,
        company=posting.company,
        title=posting.title,
        location=posting.location,
        description=posting.description,
        posted_at=posting.posted_at,
    )

    if not _is_salesforce_relevant(posting):
        return GateResult(**base, passed=False, reject_reason="not-salesforce-relevant")
    if not _is_us_or_us_remote(posting):
        return GateResult(**base, passed=False, reject_reason="not-us-or-us-remote")
    if not _within_days(posting, posted_within_days):
        return GateResult(**base, passed=False, reject_reason=f"older-than-{posted_within_days}-days")

    return GateResult(**base, passed=True, flags=_flags(posting))


def dedupe_key(posting: RawPosting) -> str:
    """Cross-source dedupe key: normalized company + title + location."""
    norm = lambda s: re.sub(r"\s+", " ", s.strip().lower())
    return f"{norm(posting.company)}|{norm(posting.title)}|{norm(posting.location)}"
