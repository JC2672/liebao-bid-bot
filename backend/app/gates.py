"""Hard gates + soft flags applied to fetched postings.

Gates reject (with a stored reason, shown not discarded). Flags are informational
badges the UI shows on passing rows. See docs/ARCHITECTURE.md "Fetch: sources & gates".

Relevance and location used to be hardcoded Salesforce/US-only logic here
and in several source modules directly (`_is_salesforce_relevant`,
`_is_us_or_us_remote`, both imported straight into dice_source.py,
ats_boards_source.py, monster_source.py, jobspresso_source.py).
Generalized to `is_field_relevant`/`is_located_or_remote_in`, driven by a
Profile's own FieldConfig/country rather than fixed constants - see
fields.py. The US rule's own logic (state abbreviations, the "bare Remote
with no country = ambiguous but accepted" call) is kept completely
unchanged and still used verbatim for country="United States" - this was
a deliberate, carefully-tuned rule and nothing about generalizing it should
regress it. Any OTHER country gets a much simpler country-name-or-remote-
scoped-to-it fallback for now; giving a new country the US rule's own level
of care (abbreviation lists, real edge cases) is exactly the kind of
per-country work to do later once a real field/profile needs it, not to
guess at here.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .models import FieldConfig, GateResult, RawPosting

# --- Field relevance -------------------------------------------------

_NEVER_MATCHES = re.compile(r"(?!)")  # a pattern with no possible match


def _keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern:
    if not keywords:
        return _NEVER_MATCHES
    # re.escape also escapes spaces; swap those back to \s+ so a multi-word
    # keyword ("lightning web component") still tolerates irregular
    # whitespace in scraped text, same as the original hand-written regexes.
    escaped = [re.escape(k.strip()).replace(r"\ ", r"\s+") for k in keywords if k.strip()]
    if not escaped:
        return _NEVER_MATCHES
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


@lru_cache(maxsize=32)
def _compile_relevance_matcher(allow: tuple[str, ...], deny: tuple[str, ...]) -> tuple[re.Pattern, re.Pattern]:
    return _keyword_pattern(allow), _keyword_pattern(deny)


def is_field_relevant(posting: RawPosting, field: FieldConfig) -> bool:
    # Title-only, not title+description: a passing tool mention buried in a
    # long description is not enough on its own - confirmed as a real,
    # common false-positive pattern live (Indeed): "Healthcare Sales
    # Director" passed because its JD said "...tracking in Salesforce",
    # despite the role having nothing to do with Salesforce development/
    # administration. Some sources don't fetch full descriptions at all
    # (Dice, Jobgether, Talent.com), so this also makes gating consistent
    # across sources rather than accidentally stricter for ones that happen
    # to return rich description text.
    allow_re, deny_re = _compile_relevance_matcher(tuple(field.relevance_allow), tuple(field.relevance_deny))
    if not allow_re.search(posting.title):
        return False
    if deny_re.search(posting.title):
        return False
    return True


# --- Location / Remote -----------------------------------------------------

US_STATE_ABBR = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
US_LOCATION_RE = re.compile(
    rf"\b(united\s+states|usa|u\.s\.a?\.?)\b|,\s*(?:{US_STATE_ABBR})\b",
    re.IGNORECASE,
)
US_NAMES = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}
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


def _country_name_re(country: str) -> re.Pattern:
    return re.compile(re.escape(country.strip()), re.IGNORECASE)


def _remote_elsewhere_re(country: str) -> re.Pattern:
    return re.compile(
        r"remote\s*[-–—(]\s*(?!" + re.escape(country.strip()) + r")[a-z]", re.IGNORECASE
    )


def _location_scope_re(country: str) -> re.Pattern:
    """Whatever "explicitly scoped to this country" means for the _flags
    remote-unscoped check below - the real US regex for the US, the simple
    name-match fallback for anything else."""
    return US_LOCATION_RE if country.strip().lower() in US_NAMES else _country_name_re(country)


def is_located_or_remote_in(posting: RawPosting, country: str) -> bool:
    if country.strip().lower() in US_NAMES:
        return _is_us_or_us_remote(posting)

    loc = posting.location or ""
    country_re = _country_name_re(country)
    remote_elsewhere_re = _remote_elsewhere_re(country)
    if remote_elsewhere_re.search(loc):
        return False
    if country_re.search(loc):
        return True
    if REMOTE_RE.search(loc) and not remote_elsewhere_re.search(loc):
        return True
    if posting.is_remote and not remote_elsewhere_re.search(loc):
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


def _flags(posting: RawPosting, country: str) -> list[str]:
    text = f"{posting.title}\n{posting.location}\n{posting.description}"
    loc = posting.location or ""
    flags: list[str] = []
    if NO_SPONSORSHIP_RE.search(text):
        flags.append("no-sponsorship")
    if C2C_RE.search(text):
        flags.append("c2c")
    if W2_ONLY_RE.search(text):
        flags.append("w2-only")
    if AGENCY_RE.search(text):
        flags.append("agency")
    if HYBRID_RE.search(loc):
        flags.append("hybrid")
    if REMOTE_RE.search(loc) and not _location_scope_re(country).search(loc):
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


def apply_gates(posting: RawPosting, field: FieldConfig, country: str, posted_within_days: int = 7) -> GateResult:
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

    if not is_field_relevant(posting, field):
        return GateResult(**base, passed=False, reject_reason=f"not-{field.id}-relevant")
    if not is_located_or_remote_in(posting, country):
        return GateResult(**base, passed=False, reject_reason="not-in-country-or-remote")
    if not _within_days(posting, posted_within_days):
        return GateResult(**base, passed=False, reject_reason=f"older-than-{posted_within_days}-days")

    return GateResult(**base, passed=True, flags=_flags(posting, country))


def dedupe_key(posting: RawPosting) -> str:
    """Cross-source dedupe key: normalized company + title + location."""
    norm = lambda s: re.sub(r"\s+", " ", s.strip().lower())
    return f"{norm(posting.company)}|{norm(posting.title)}|{norm(posting.location)}"
