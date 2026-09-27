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

**Sources** (each behind one `fetch(query) -> RawPosting[]` adapter). None of
the ten need login or an API key - see each module's docstring for how it was
verified, since first impressions from web search alone were wrong twice
(Jobright and Jobgether both looked account-gated/blocked until inspected
directly with a real browser):

| Source | How | Notes |
|---|---|---|
| LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs | [JobSpy](https://github.com/speedyapply/JobSpy) | unofficial, rate-limit-sensitive |
| Dice | HTML scrape, plain `requests` | own API shut down years ago; card-level only, no per-listing JD fetch |
| Remotive | public JSON API | keeps to its own asked rate limit (fetch is on-demand only, never polled) |
| RemoteOK | public JSON API, plain `requests` | `curl` on Windows hangs against this host (schannel TLS quirk) - `requests`/urllib3 has no such issue |
| We Work Remotely | public RSS (combined "all jobs" feed, no keyword param) | |
| Jobright | plain `requests`, reads the page's embedded `__NEXT_DATA__` JSON | richest data of any source (salary, H1B signal, seniority, remote/hybrid); only page 1 (~20 results) is reachable, `&page=` doesn't paginate the SSR payload |
| Jobgether | **Playwright** (headless Chromium), DOM read | plain requests get HTTP 403 from Cloudflare on this one specifically; a real browser gets through with no login involved |

**Login-gated sources:** none needed one so far. If a genuinely account-gated
source comes up later, the plan is a Playwright **persistent-context**
profile per source: a "Sign in" action opens a real, visible browser window
for the user to log in once, the resulting `storage_state` (cookies) is saved
to disk, and later headless fetches reuse it. Not built, because nothing has
required it yet.

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
├─ extension/                   # WXT ChatGPT worker
├─ data/                        # gitignored: sqlite db, staging/
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
