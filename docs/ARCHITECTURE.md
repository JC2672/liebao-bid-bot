# liebao-bid-bot — Architecture

Single-user job-application assistant for US/Remote Salesforce roles, with multiple
independent "profiles" (each profile = a different real identity/resume/prompt).

The system has two independently-run parts that share nothing except the on-disk
SQLite queue and per-profile Google Sheets:

1. **Fetch** — pull job postings from several sources, apply hard filters, let you
   shortlist in Excel, then import the shortlist into a queue for one profile.
2. **Generate & Apply** — churn through a profile's queue, produce a tailored
   resume PDF per opportunity via ChatGPT web (or the API as a fallback), and let
   you review/apply, at which point the application is filed to disk and logged
   to that profile's Google Sheet tab.

```
┌─── Part 1: Fetch (stateless) ──────────────────┐   ┌─── Part 2: Generate & Apply ───────────────────┐
│ Sources → Normalize → Dedupe (within run) →     │   │ SQLite queue: queued → generating → ready      │
│ Hard gates (Salesforce/US-Remote) → Flags       │   │                          ↘ failed → [Retry]    │
│   ↓                                              │   │                                                 │
│ Results table (in-memory) → [Export XLSX]        │   │ Engine (ChatGPT web via extension, API fallback)│
└──────────────────────────────────────────────────┘   │   ↓                                             │
        you prune the XLSX by hand in Excel            │ Ready row: [Open Post] [Open Folder]            │
        ↓                                               │            [Applied] [Remove]                   │
[Import] pick profile → dedupe vs. that profile's       │   ↓ Applied                                     │
Sheet tab + current queue → insert rows as `queued`     │ 1. create <Output Root>/<Company - Title - Date>│
        ↓                                               │ 2. move staged PDF + JD.txt into it             │
   SQLite `opportunities` table  ◀──────────────────────┤ 3. append row to profile's Sheet tab            │
                                                          │ 4. delete the SQLite row + staging files        │
                                                          └─────────────────────────────────────────────────┘
```

## Why this shape

- **No jobs database.** Fetch results are never persisted; they're a transient
  table you export, prune in Excel, and re-import. This keeps Part 1 stateless
  and easy to re-run, and avoids a stale "seen jobs" table growing forever.
- **SQLite is a work queue, not a system of record.** It only ever holds
  opportunities that are queued/generating/ready/failed for *some* profile.
  The moment one is applied, its row is deleted — SQLite always reflects "what's
  left to do", nothing more.
- **The Output Root is the system of record for applications.** A folder only
  exists there if you actually applied. The Google Sheet is the durable,
  human-readable log and the source of dedupe truth per profile.
- **Profiles are separate people,** not variants of one person: separate prompt,
  separate resume template, separate contact info, separate Sheet tab, separate
  configurable Output Root. One ChatGPT account is shared across all profiles,
  using Temporary Chat (or memory off) so one profile's details can't leak into
  another's resume.
- **LLM output is JSON, never HTML.** The template controls layout/section order
  deterministically; the LLM only ever fills in a fixed schema. This is a direct
  fix for the section-order corruption seen in the earlier HTML-generation
  experiment.
- **Placeholders `{NAME}`, `{PHONE}`, etc. are substituted by the app, not the
  LLM.** Contact info never enters the prompt and can never be garbled by the
  model.

## Data model

### SQLite — `opportunities` table (the only table)

| column | notes |
|---|---|
| id | PK |
| profile | which profile this belongs to |
| company, title, location, source, url | from the fetch |
| description | full JD text, used as the prompt's JD input |
| status | `queued` \| `generating` \| `ready` \| `failed` |
| error | set when status = failed |
| resume_json | the parsed LLM output, once generated |
| staging_dir | path to `data/staging/<id>/` holding the generated PDF + JD.txt |
| created_at, updated_at | |

### Per-profile config — `profiles/<id>/profile.json`

Profiles are created, edited, and deleted from the **Profiles screen** in the
UI, not hand-edited. Each still lives on disk as a plain directory so nothing
about the rest of the system (generation, staging, Output Root) has to change:

```jsonc
// profiles/<id>/profile.json - id is a slug auto-derived from the name
{
  "id": "firstname-lastname",
  "name": "Firstname Lastname",
  "location": "",
  "phone": "",
  "email": "",
  "linkedin": "",
  "sheet_id": "",                     // Google Sheet ID (optional until Applied is used)
  "sheet_tab": "Firstname",           // tab name in that Sheet
  "output_root": "F:/Applications/Firstname",
  "template": "template.html"
}
```
Plus `prompt.md` (the tailoring prompt, JD gets appended) and `template.html`
(the resume layout for this profile — starts as a copy of the shared
`profiles/_default_template.html` on creation, then can be customized
per-profile). Deleting a profile is blocked while it still has opportunities
in the SQLite queue, to avoid silently orphaning in-flight work.

Deliberately no `title` field here: a resume's headline title varies per JD
and is already generated per-opportunity (see the resume JSON schema below),
so a fixed per-profile one would just be redundant/stale. `output_root` is
never hand-typed either - the Profiles screen's "Browse…" button opens a
native OS folder picker (`POST /pick-folder`) and fills in the real path,
since a browser's own picker can't hand back an absolute filesystem path.

### Resume JSON schema (LLM output contract)

```jsonc
{
  "name": "{NAME}", "title": "", "location": "{LOCATION}",
  "phone": "{PHONE}", "email": "{EMAIL}", "linkedin": "{LINKEDIN}",
  "summary": "",
  "skills": [{ "category": "", "items": "" }],
  "experience": [{
    "company": "", "location": "", "title": "", "dates": "",
    "project": "", "bullets": []
  }],
  "education": [{ "school": "", "degree": "", "year": "", "details": "" }],
  "certifications": []
}
```
Parsing is tolerant of code fences and trailing commas from ChatGPT's output;
anything that still fails schema validation sets the row to `failed` with a
readable error instead of silently producing a bad PDF.

### Google Sheet (one tab per profile)

Columns: `Date`, `Company`, `Title`, `Source`, `Job URL`.
Dedupe on import checks only the current profile's tab (normalized Job URL,
falling back to Company+Title).

### On-disk layout on Applied

```
<Output Root for profile>/
└─ Acme Corp - Senior Salesforce Developer - 2026-09-27/
   ├─ Firstname_Lastname.pdf
   └─ JD.txt
```

## Fetch: sources & gates

**Sources** (each behind one
`fetch(query, posted_within_days) -> RawPosting[]` adapter - most sources
ignore `posted_within_days` since gates.py's own recency gate filters
client-side anyway, but a source whose own API can filter server-side
should use it: pulling a fixed-size page sorted by relevance/default rather
than by date can otherwise miss genuinely recent postings entirely if they
don't also rank high on relevance - a real bug, found live, in Jobright).
Similarly, `query` free text isn't equally well-suited to every source's own
matching behavior - Jobright's is now confirmed to need a seeded list of
real role titles rather than the generic default (see its row below); other
sources haven't been checked this closely yet and may have their own
quirks worth understanding the same way, one at a time, rather than
assumed to all behave like Jobright's did.
None of the seventeen need login or an API key - see each module's docstring for how
it was verified, since first impressions (from web search, from a sibling
local project's own config, or from a site's own published docs) have been
wrong more than once: Jobright and Jobgether both looked account-gated/
blocked until inspected directly with a real browser; Himalayas' own OpenAPI
spec documents a search endpoint that returns a genuine live 404; a prior
draft of the Greenhouse/Lever/Ashby company list, copied from that sibling
project, turned out to be badly stale (63 of 192 tokens tried actually
resolved). Every source below and every company-board token was checked live
before being added, not assumed from a doc or another project's config:

| Source | How | Notes |
|---|---|---|
| LinkedIn | [JobSpy](https://github.com/speedyapply/JobSpy), `location="United States"` | "remote only" was asked for, but neither achievable lever actually narrows to *US* remote: JobSpy's `is_remote=True` flag sends LinkedIn's real `f_WT=2` filter param, but was verified live to have **zero effect** (identical top-15 results with and without it, checked via both the raw HTTP response and JobSpy's own parser) - LinkedIn's guest/anonymous endpoint appears to just not honor it anymore. `location="Remote"` *does* genuinely change the result set, but worldwide rather than US-specific (mostly Poland/India/Vietnam-type postings the US-location gate then discards) - a worse trade than `location="United States"`, where every result is at least US-based even if not every one is remote. "Exclude Easy Apply" is **not achievable at all**: LinkedIn's own search only offers an "Easy Apply ONLY" filter, no exclude option, and JobSpy's LinkedIn scraper never even records whether a posting is Easy Apply |
| Indeed, Glassdoor, ZipRecruiter, Google Jobs | [JobSpy](https://github.com/speedyapply/JobSpy) | unofficial, rate-limit-sensitive |
| Dice | HTML scrape, plain `requests` | own API shut down years ago; card-level only, no per-listing JD fetch |
| Remotive | public JSON API | keeps to its own asked rate limit (fetch is on-demand only, never polled) |
| RemoteOK | public JSON API, plain `requests` | `curl` on Windows hangs against this host (schannel TLS quirk) - `requests`/urllib3 has no such issue. `tags` is an exact single-word match, not free text - first word of the query is used as the tag, falling back to a client-side filter over the general feed if that tag doesn't exist |
| We Work Remotely | public RSS (combined "all jobs" feed, no keyword param) | |
| Jobright | plain `requests` - anonymous (`__NEXT_DATA__` JSON) or authenticated (`/swan/recommend/search`, run concurrently across `SEED_TITLES`), whichever session is available | anonymous: page 1 only (~20 results, no pagination control exists to click, unlike Talent.com), and as of this writing the anonymous search *page* has started showing a Cloudflare "Security check" challenge (confirmed live - it returned clean, rich results earlier in this project; the same request now returns a challenge page). The API endpoint itself is unaffected (confirmed: still returns a clean JSON 401 for a missing/bad session, not a challenge) - see "Login-gated sources" below. `posted_within_days` is passed through as `daysAgo`, a genuine server-side recency filter confirmed live (result counts scale sensibly with it) - this was a real bug for a while: without it, results are a fixed-size relevance-sorted window that can miss almost everything actually posted recently, since gates.py's own recency gate can only discard from what was fetched, not recover what wasn't. Caught from a live discrepancy the user found: a `posted_within_days=1` fetch returned 1 result against a manual browser search showing 20+ - fixed. **Separately**, the authenticated path no longer uses the caller's free-text `query` at all: watched Jobright's own UI live and confirmed a bare `value="Salesforce"` search is a real trap - every single result was a job *at* Salesforce Inc itself (generic corporate roles, not Salesforce-skill roles at other companies), because the site's relevance ranking for a company-shaped term favors literal company-name matches. Typing an actual role title into the same UI (e.g. "Salesforce Developer") produced genuinely relevant results at real client companies. So the authenticated path now runs a fixed list of ~32 seed role titles (`SEED_TITLES` - Salesforce Administrator/Developer/Consultant/Architect/Technical Architect/Solutions Architect/Engineer, Marketing Cloud Developer, MuleSoft Developer, Salesforce CPQ, Health/Data/Service/Revenue Cloud, OmniStudio, Agentforce, etc.) through the search concurrently and dedupes by job ID, rather than a single generic query - the same fix a sibling local project already carries under its own `jobrightTitles` config (independently rediscovered here by watching the real UI, not copied from that config). The list was expanded a second time by probing candidate titles against the real API and checking actual result counts/samples, not by guessing: "Salesforce Technical Architect" (36 real matches) and "Salesforce Solutions Architect" (75) turned out highly productive and were added; "Tableau CRM" and "Experience Cloud" looked plausible by name but turned out polluted by unrelated Adobe/BI results and were deliberately left out. Also fixed: `workModel` is now `[2]` (Remote) rather than unrestricted - confirmed live that a bare "Salesforce" + Remote search (574 total matches) was *still* dominated by Salesforce Inc itself (all 200 checked were the company, zero exceptions), so this wasn't solely a query-text problem. Confirmed live after both fixes: "Salesforce"-the-company dropped to ~15% of results (35 of 227 passing), all `Remote - United States`, real client/consulting companies (Perficient, Cognizant, Cherokee Federal, CrossCountry Consulting, fusionSpan, etc.) filling the rest |
| Jobgether | **Playwright** (headless Chromium), DOM read | plain requests get HTTP 403 from Cloudflare on this one specifically; a real browser gets through with no login involved |
| Himalayas | public JSON API, plain `requests` | its `/jobs/api/search?q=` endpoint is documented (in its own OpenAPI spec) but returns a live 404 - confirmed with a cache-busting param to rule out a stale CDN cache. Only `/jobs/api` (browse, cursor-paginated) is actually live, so this pulls a few pages of the most recent postings and filters client-side |
| Jobicy | public JSON API | `tag` param genuinely filters server-side (unlike RemoteOK's); each job carries a real `jobGeo` field |
| Arbeitnow | public JSON API, plain `requests` | no server-side search despite accepting `search`/`tags`/`q` params (all silently return the same unfiltered list, verified) - browse-only, filtered client-side |
| Working Nomads | public JSON API, plain `requests` | same as Arbeitnow: no working filter param, small feed, filtered client-side |
| Greenhouse, Lever, Ashby | direct per-company public JSON APIs, plain `requests`, fanned out concurrently | no cross-company search - each is one call per company's own board. `query` is unused (like We Work Remotely); gates.py's relevance filter does the real work over every job each company in the list has open. Company list lives in `ats_boards_source.py`, each token verified live before being added - re-verify before trusting an old copy of this list, since companies migrate ATS providers over time (this project's own first draft of the list, borrowed from elsewhere, was already a third stale) |
| Talent.com | **Playwright** (headless Chromium), DOM read, clicks through pages | no official free API (only paid third-party scrapers exist); the search page loads fine (no Cloudflare block) but its visible job cards come from a client-side Next.js RSC request, not the initial HTML (which only has a bare SEO link list) - not a stable JSON API worth reverse-engineering, so this reads the rendered DOM like Jobgether. Pagination is a "Next page" button, not a URL param - since a real browser is already open for this source, it just clicks it (up to `MAX_PAGES`), confirming each click actually changed the result set before continuing. Contrast with Jobright below, which has no pagination control at all to click |

**Investigated and not integrated:** The Muse - its public API has no
free-text search and no category matching Salesforce/CRM, and is 400k+ jobs
total, so scanning enough pages to find relevant postings isn't practical the
way it is for the other browse-and-filter sources above (each of those is
only tens-to-low-hundreds of postings total). Obra - its web app is gated
behind **Firebase App Check**, a purpose-built anti-automation service
(distinct from incidental Cloudflare bot-protection): a single real-browser
visit hit a 403 that self-throttled further attempts for 24 hours. That's a
deliberate anti-scraping measure, not something worth working around.

**Login-gated sources:** built for Jobright, the first source that actually
benefits from it (its authenticated API returns far more than the ~20-result
anonymous cap, and the anonymous page itself is now Cloudflare-challenged -
see above). This uses the user's **real, already-open Chrome** via a small
companion extension (`extension/` - plain Manifest V3, no build step, loaded
unpacked; see its own README) - not a separate automation profile the user
would have to log into a second time (an earlier version of this did exactly
that and was the wrong shape for it).

How it fits together:
- `extension/content-script.js` runs only on the web app's own origin
  (`localhost`/`127.0.0.1:5173`) and relays `window.postMessage` calls from
  the page to `extension/background.js` (a service worker) and back -
  content scripts can't call `chrome.cookies`/`chrome.tabs` directly, only
  the background script can.
- `background.js` handles two messages: read the user's actual
  `jobright.ai` cookies (`chrome.cookies.getAll`) and POST them to the local
  backend, or open a new tab to Jobright's login page
  (`chrome.tabs.create`).
- `web/src/lib/extensionBridge.ts` is the frontend half of that handshake:
  `isExtensionInstalled()` (a "ready" ping the content script sends so the
  page can tell whether the extension exists at all, rather than hanging
  forever), `checkJobrightSession()`, `openJobrightLoginTab()`.
- `POST /sources/jobright/cookies` (backend) receives those cookies from
  the extension and saves them to `data/browser-sessions/jobright/` -
  gitignored - returning whether they actually work: a real live request to
  the authenticated API, not just "were cookies received" (confirmed live:
  Jobright's API returns a clean, unambiguous signal for an invalid/missing
  session - HTTP 401, `{"success": false, "errorCode": 41001, "errorMsg":
  "Cookie not found"}`).
- `jobright_source.py` loads those saved cookies and attaches them as a
  plain `Cookie` header on ordinary `requests` calls to the real API - no
  browser involved in the fetch itself, only in obtaining the cookies.
  Falls back to the anonymous path automatically when no valid session
  exists.

Fetch tab UI/flow, run fresh on every Run Fetch click when Jobright is
selected (not just checked once and cached): if the extension isn't
detected at all, warn and continue with anonymous access only; if the
extension is present but the session check comes back not-logged-in, open
a Jobright sign-in tab automatically, show a message to sign in and click
Run Fetch again, and **don't fetch this round** - the second click, now
signed in, goes through normally.

Not yet verified with a real Jobright account (I have none) - the
end-to-end mechanics (cookie relay, live session validation, falling back
to the anonymous path) are all confirmed working with synthetic cookies,
but the authenticated `/swan/recommend/search` response shape is assumed to
match a sibling project's equivalent client, not independently confirmed
against real logged-in data.

For any other source that turns out to be genuinely account-gated, the same
extension can grow another cookie-domain + message-type pair rather than
needing a whole new mechanism.

**Open question, not yet decided:** whether to keep scraping LinkedIn at all.
A comparable local project (a sibling job-capture tool covering much of this
same source list) deliberately excludes LinkedIn entirely as a matter of
policy, given how aggressively LinkedIn enforces against scraping. This
project currently still includes it via JobSpy.

**Hard gates** (reject, with a stored reason shown in the UI):
- Salesforce relevance (keyword allow-list + negative list, to exclude
  "Account Executive at Salesforce Inc." style false positives)
- US-located or explicitly Remote-US (location string parsing, not just the
  word "remote" — catches "Remote – India", "Remote (EMEA)")
- Posted within N days (default 7, configurable on the fetch screen)

**Flags** (shown, not rejected): no-sponsorship/citizens-only, C2C/W2-only,
staffing agency, hybrid.

Within-run dedupe: exact (URL/ATS id) and cross-source (hash of
company+normalized title+location).

## Generation engine

1. Take next `queued` row for the active profile → `generating`.
2. Build prompt = profile's `prompt.md` + this opportunity's `description`.
3. Send via **ChatGPT web** (Chrome extension, Temporary Chat) — API fallback
   togglable for when web is capped or backed up. Manual copy/paste mode exists
   as a bootstrap/fallback path.
4. Parse → validate against schema → substitute `{PLACEHOLDER}` fields from
   `profile.json` → render `template.html` → print to PDF (headless Chromium)
   → write PDF + JD.txt to `data/staging/<id>/`.
5. Row → `ready`. On any failure → `failed` + error, retryable.

Queue screen actions per row: **Open Post** (new tab), **Open Folder** (opens
the staging dir via the backend, since browsers can't open local folders),
**Applied** (files the application per "On disk layout" above, appends to the
Sheet, deletes the row), **Remove** (drops the row + staging files, nothing
recorded).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.14 + FastAPI + SQLite (stdlib `sqlite3`) | JobSpy and the ATS scraping ecosystem are Python; FastAPI serves the local UI and exposes an OpenAPI spec for typed frontend clients |
| Frontend | React + Vite + TypeScript + shadcn/ui + TanStack Query/Table | clean, structured UI without a heavy design system |
| Extension | WXT (Manifest V3, TypeScript) | drives your real, logged-in ChatGPT session; talks to the backend over `localhost` |
| PDF | Jinja2 template → HTML → headless Chromium `page.pdf()` (Playwright) | pixel-accurate, template fully controls layout |
| Sheets | Google service account + `gspread` | no OAuth login flow; you share the Sheet with the service account's email once |

## Repo layout

```
liebao-bid-bot/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ db.py                 # sqlite connection + schema
│  │  ├─ models.py             # pydantic models
│  │  ├─ sources/               # one module per source adapter
│  │  ├─ gates.py               # hard filters
│  │  ├─ sheets.py               # gspread wrapper
│  │  ├─ pdf.py                  # jinja2 + playwright render
│  │  └─ routers/
│  │     ├─ fetch.py            # POST /fetch, GET /fetch/export
│  │     ├─ queue.py            # import, list, applied, remove, retry
│  │     └─ profiles.py
│  ├─ profiles/
│  │  └─ <profile-name>/ profile.json, prompt.md, template.html
│  └─ pyproject.toml
├─ web/                         # React app
├─ extension/                   # companion extension (Jobright session today;
│                                #   Phase 3's ChatGPT-web worker likely lives
│                                #   here too - plain Manifest V3 for now, no
│                                #   WXT build step, since nothing has needed one yet)
├─ data/                        # gitignored: sqlite db, staging/, browser-sessions/
└─ docs/
   └─ ARCHITECTURE.md
```

## Build phases

1. **Fetch screen** — sources, hard gates + flags, results table, XLSX export.
2. **Import + Queue screen** — profile picker, dedupe vs. Sheet, SQLite queue,
   manual-paste generation path (prompt→you paste ChatGPT's JSON→PDF renders),
   Open Post/Open Folder/Applied/Remove, Sheet append on Applied.
3. **ChatGPT web worker** (extension) replacing manual paste; API fallback.
4. **More sources, Dice in particular; polish and error handling.**

Each phase is independently useful and gets its own commit(s).
