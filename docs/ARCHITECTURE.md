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
│ Results table (in-memory) → [Export XLSX]        │   │ Engine (ChatGPT web via a dedicated browser)    │
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
  "sheet_webapp_url": "",              // Apps Script Web App URL (optional until Applied is used)
  "sheet_secret": "",                  // shared secret that Web App checks - see docs/apps-script.gs
  "sheet_tab": "Firstname",           // tab name in that Sheet
  "output_root": "F:/Applications/Firstname",
  "template_id": "default"            // live reference into templates/ - see below
}
```
Plus `prompt.md` (the tailoring prompt, JD gets appended). Deleting a
profile is blocked while it still has opportunities in the SQLite queue, to
avoid silently orphaning in-flight work.

Deliberately no `title` field here: a resume's headline title varies per JD
and is already generated per-opportunity (see the resume JSON schema below),
so a fixed per-profile one would just be redundant/stale. `output_root` is
never hand-typed either - the Profiles screen's "Browse…" button opens a
native OS folder picker (`POST /pick-folder`) and fills in the real path,
since a browser's own picker can't hand back an absolute filesystem path.

### Templates — `templates/<id>/` (independent of Profiles)

Templates are their own entity, managed from a **Templates screen** exactly
like Profiles are - not owned by any one profile. A profile references one
by id (`Profile.template_id`), and that reference is *live*, not a
snapshot: editing a template changes what every profile using it renders on
its next generation, with no per-profile copy to keep in sync. This
replaced an earlier shape where each profile got its own `template.html`,
seeded from a shared default on creation - real friction the moment you
want to improve the design once and have it apply everywhere, and pure
accident anyway: the template only ever needed `resume_json` plus the
profile's contact fields at render time, never anything profile-specific
baked into the file itself.

```
templates/<id>/
  template.json   # { "id": "...", "name": "..." }
  template.html   # Jinja2 source, see resume_render.py
```

`GET /templates/<id>/preview.html` and `.../preview.pdf` render a template
against fixed sample data (`resume_render.SAMPLE_CONTACT` +
`SAMPLE_RESUME_JSON`), so a template can be designed and previewed without
Phase 3's ChatGPT engine existing yet - the Templates screen's card grid
embeds the HTML preview live (scaled down) and links out to the full PDF.
PDF rendering reuses Playwright (already a dependency for the Jobgether/
Talent.com sources): render the Jinja2 HTML, `page.set_content()`, then
`page.pdf()` with Letter-size margins - the same "render HTML, print it"
shape as a real generation will eventually use, just against sample data
instead of a real opportunity. Deleting a template is blocked while any
profile still references it (mirrors the opportunities-in-queue guard on
deleting a profile).

One real Jinja2 gotcha hit building the default template: `{{ s.items }}`
on a skills entry silently returned `dict.items`' bound method instead of
the `"items"` key's value, since Jinja2's attribute lookup tries `getattr`
before `__getitem__` and `dict` has a real `.items` method. Fixed with
bracket access (`{{ s['items'] }}`) rather than renaming the schema field -
worth knowing before adding more dict-shaped fields to the resume JSON
schema below, since `keys`/`values`/`get` are the same trap.

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

`POST /queue/{id}/applied` (queue.py's `mark_applied`) does, in this exact
order: (1) append a row to the profile's Sheet, (2) move the staging
folder's contents into the destination above and delete the now-empty
staging folder, (3) delete the opportunity row. The Sheet append happens
*first* on purpose - it used to happen last, which meant a Sheet failure
(missing config, network hiccup) left a row stuck: files already moved to
the real output folder, but the queue row still `ready` with a
`staging_dir` that no longer existed, so it could never be retried
cleanly. Appending first means a failure there leaves everything
untouched - fix the Sheet config, click Applied again.

The Sheet itself is reached through a Google Apps Script Web App bound to
that spreadsheet (`docs/apps-script.gs`), not a service account - see
`sheets.py`'s module docstring for the reasoning (no Cloud project, no key
file to protect; the real tradeoff is a shared secret standing in for
Google-level auth, since a deployed Web App's URL alone isn't
authenticated). A profile's `sheet_webapp_url` + `sheet_secret` point at
that deployment; `sheet_tab` selects which tab within it. The script
auto-creates a profile's tab (with the header row) on first use, same as
`gspread`'s `add_worksheet` used to do directly.

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
None but Jobright need login or an API key - see each module's docstring for how
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
| LinkedIn | [JobSpy](https://github.com/speedyapply/JobSpy), `location="United States"`, `linkedin_fetch_description=True` | "remote only" was asked for, but neither achievable lever actually narrows to *US* remote: JobSpy's `is_remote=True` flag sends LinkedIn's real `f_WT=2` filter param, but was verified live to have **zero effect** (identical top-15 results with and without it, checked via both the raw HTTP response and JobSpy's own parser) - LinkedIn's guest/anonymous endpoint appears to just not honor it anymore. `location="Remote"` *does* genuinely change the result set, but worldwide rather than US-specific (mostly Poland/India/Vietnam-type postings the US-location gate then discards) - a worse trade than `location="United States"`, where every result is at least US-based even if not every one is remote. "Exclude Easy Apply" is **not achievable at all**: LinkedIn's own search only offers an "Easy Apply ONLY" filter, no exclude option, and JobSpy's LinkedIn scraper never even records whether a posting is Easy Apply. `linkedin_fetch_description=True` (default is `False`) makes JobSpy visit each job's own page for the real JD, rather than only reading the search-card - without it, gates.py's flags (no-sponsorship, C2C/W2-only, staffing-agency) can never fire on LinkedIn rows since they scan description text (title relevance itself is unaffected, since gates.py matches title-only). Costs one extra request per result, so slower and a somewhat higher chance of LinkedIn rate-limiting than the card-only default - accepted tradeoff for working flags. Verified live: 50/50 results came back with a real, non-empty description afterward |
| Dice | HTML scrape, plain `requests`, plus one extra `requests` GET per title-relevant result for the real description | its old API is gone, so the search-results page is still scraped for cards as before; a bare `query="Salesforce"` isn't a trap here though (confirmed live: 142/166 results already title-relevant, no company-name-match problem). Checked how a sibling local project handles descriptions here - it uses Playwright to visit each job's own page, but that's not actually needed: each Dice job-detail page embeds a real `application/ld+json` `JobPosting` block in the plain server-rendered HTML (no Cloudflare block on detail pages either, confirmed live, status 200), so a plain `requests` GET gets the full JD. Only fetched for postings that already pass the title-relevance gate, not all of them - no point paying for a detail request that's going to be discarded anyway. Verified live: 142/142 relevant results came back with a real description afterward |
| Indeed | [JobSpy](https://github.com/speedyapply/JobSpy), fanned out over `SALESFORCE_TITLES` (same shared list Jobright uses, see below) | a bare `query="Salesforce"` is a similarly weak search on Indeed as it was on Jobright: confirmed live, 50 fetched but only 2 passed gates.py's relevance gate, both from the same company, vs. `query="Salesforce Developer"` alone getting 19 of 50 to pass. So this ignores the caller's free-text query and instead runs the shared `SALESFORCE_TITLES` list concurrently (4 workers, lower than Jobright's 8, and a smaller per-title result cap - Indeed is known to be stricter about scraping than Jobright turned out to be), deduping by URL. Verified end-to-end: 117 passing results vs. 2 before, real companies (Deloitte, BCG, Fortinet, etc.) |
| Remotive | public JSON API | keeps to its own asked rate limit (fetch is on-demand only, never polled) |
| RemoteOK | public JSON API, plain `requests` | `curl` on Windows hangs against this host (schannel TLS quirk) - `requests`/urllib3 has no such issue. `tags` is an exact single-word match, not free text - first word of the query is used as the tag, falling back to a client-side filter over the general feed if that tag doesn't exist |
| We Work Remotely | public RSS (combined "all jobs" feed, no keyword param) | |
| Jobright | plain `requests` - anonymous (`__NEXT_DATA__` JSON) or authenticated (`/swan/recommend/search`, run concurrently across `SEED_TITLES`), whichever session is available | anonymous: page 1 only (~20 results, no pagination control exists to click, unlike Talent.com), and as of this writing the anonymous search *page* has started showing a Cloudflare "Security check" challenge (confirmed live - it returned clean, rich results earlier in this project; the same request now returns a challenge page). The API endpoint itself is unaffected (confirmed: still returns a clean JSON 401 for a missing/bad session, not a challenge) - see "Login-gated sources" below. `posted_within_days` is passed through as `daysAgo`, a genuine server-side recency filter confirmed live (result counts scale sensibly with it) - this was a real bug for a while: without it, results are a fixed-size relevance-sorted window that can miss almost everything actually posted recently, since gates.py's own recency gate can only discard from what was fetched, not recover what wasn't. Caught from a live discrepancy the user found: a `posted_within_days=1` fetch returned 1 result against a manual browser search showing 20+ - fixed. **Separately**, the authenticated path no longer uses the caller's free-text `query` at all: watched Jobright's own UI live and confirmed a bare `value="Salesforce"` search is a real trap - every single result was a job *at* Salesforce Inc itself (generic corporate roles, not Salesforce-skill roles at other companies), because the site's relevance ranking for a company-shaped term favors literal company-name matches. Typing an actual role title into the same UI (e.g. "Salesforce Developer") produced genuinely relevant results at real client companies. So the authenticated path now runs a fixed list of ~32 seed role titles (`SEED_TITLES` - Salesforce Administrator/Developer/Consultant/Architect/Technical Architect/Solutions Architect/Engineer, Marketing Cloud Developer, MuleSoft Developer, Salesforce CPQ, Health/Data/Service/Revenue Cloud, OmniStudio, Agentforce, etc.) through the search concurrently and dedupes by job ID, rather than a single generic query - the same fix a sibling local project already carries under its own `jobrightTitles` config (independently rediscovered here by watching the real UI, not copied from that config). The list was expanded a second time by probing candidate titles against the real API and checking actual result counts/samples, not by guessing: "Salesforce Technical Architect" (36 real matches) and "Salesforce Solutions Architect" (75) turned out highly productive and were added; "Tableau CRM" and "Experience Cloud" looked plausible by name but turned out polluted by unrelated Adobe/BI results and were deliberately left out. Also fixed: `workModel` is now `[2]` (Remote) rather than unrestricted - confirmed live that a bare "Salesforce" + Remote search (574 total matches) was *still* dominated by Salesforce Inc itself (all 200 checked were the company, zero exceptions), so this wasn't solely a query-text problem. Confirmed live after both fixes: "Salesforce"-the-company dropped to ~15% of results (35 of 227 passing), all `Remote - United States`, real client/consulting companies (Perficient, Cognizant, Cherokee Federal, CrossCountry Consulting, fusionSpan, etc.) filling the rest |
| Jobgether | **Playwright** (headless Chromium), DOM read | plain requests get HTTP 403 from Cloudflare on this one specifically; a real browser gets through with no login involved |
| Himalayas | public JSON API, plain `requests` | its `/jobs/api/search?q=` endpoint is documented (in its own OpenAPI spec) but returns a live 404 - confirmed with a cache-busting param to rule out a stale CDN cache. Only `/jobs/api` (browse, cursor-paginated) is actually live, so this pulls a few pages of the most recent postings and filters client-side |
| Jobicy | public JSON API | `tag` param genuinely filters server-side (unlike RemoteOK's); each job carries a real `jobGeo` field |
| Arbeitnow | public JSON API, plain `requests` | no server-side search despite accepting `search`/`tags`/`q` params (all silently return the same unfiltered list, verified) - browse-only, filtered client-side |
| Working Nomads | public JSON API, plain `requests` | same as Arbeitnow: no working filter param, small feed, filtered client-side |
| Greenhouse, Lever, Ashby | direct per-company public JSON APIs, plain `requests`, fanned out concurrently | no cross-company search, and no query capability of any kind - checked live whether any of `search`/`q`/`query`/`title` do anything on Greenhouse's boards-api and all four silently returned the identical unfiltered list for a real board. So unlike Jobright, there's no server-side lever to use at all: title relevance and US-or-remote location (both reusing gates.py's own checks, not a second copy of the regexes) are applied client-side in the adapter itself, before results ever leave it. Without this the noise looked like Jobright's pre-fix problem: of ~8,900 Greenhouse jobs fanned out across every company, only ~31 even had a Salesforce-relevant title, and most of *those* were non-US offices (Bangalore, Gurugram, Warsaw, Poland, Norway...) that would've been rejected downstream anyway but still cluttered the fetch. (An interim version required an explicit "remote" qualifier in the location text specifically, rejecting bare "United States" as ambiguous - that band turned out too narrow, dropping legitimate matches like a bare "United States" Salesforce Engineer role at MongoDB, so it's back to the same US-or-remote definition every other source uses.) Company list lives in `ats_boards_source.py`, each token verified live before being added - re-verify before trusting an old copy of this list, since companies migrate ATS providers over time (this project's own first draft of the list, borrowed from elsewhere, was already a third stale). Coverage here is inherently thin: the company list skews toward big tech (Stripe, MongoDB, Okta, etc.) rather than Salesforce-consulting shops, so a modest number of genuinely relevant postings per run is expected, not a bug |
| Talent.com | **Playwright** (headless Chromium), DOM read, clicks through pages | no official free API (only paid third-party scrapers exist); the search page loads fine (no Cloudflare block) but its visible job cards come from a client-side Next.js RSC request, not the initial HTML (which only has a bare SEO link list) - not a stable JSON API worth reverse-engineering, so this reads the rendered DOM like Jobgether. Pagination is a "Next page" button, not a URL param - since a real browser is already open for this source, it just clicks it (up to `MAX_PAGES`), confirming each click actually changed the result set before continuing. Contrast with Jobright below, which has no pagination control at all to click |
| Built In | plain `requests`, fanned out over `SALESFORCE_TITLES` | added per the user's ask (a sibling local project already covers this source, using Playwright + a per-job detail visit) - neither turned out necessary, confirmed live: `builtin.com/jobs/remote?search=...` is plain server-rendered HTML with no Cloudflare block, and each search-results card *already* embeds a real description summary, work-arrangement badge, location, posted-date and top-skills list inline - no per-listing follow-up request needed at all, unlike Dice. A bare `search=Salesforce` is the same trap as Jobright/Indeed (confirmed live: 25/25 results for a bare query were sales titles - "Field Sales Representative", "Territory Account Executive" - vs. genuinely relevant results for "Salesforce Developer" alone), so this fans out over the shared `SALESFORCE_TITLES` list too. Uses `/jobs/remote` specifically (not `/jobs`), which scopes every result to remote-eligible roles by construction - confirmed live, every card's work-arrangement badge was "Remote" or "In-Office or Remote" (never "Hybrid"/"Onsite"-only) - so "work model = Remote" is satisfied by the URL itself, no extra client-side filtering needed the way Greenhouse/Lever/Ashby required. `daysSinceUpdated` is a genuine server-side recency filter (confirmed live: 0/9/25 results for 1/7/30 days on a fixed query) and `page=` genuinely paginates (confirmed live: zero ID overlap between page 1 and 2). Verified end-to-end: 23 passing results (Cherokee Federal, CGI Digital, Mozilla, Voyager Technologies, etc.) |
| Jobspresso | plain `requests`, fanned out over `SALESFORCE_TITLES`, plus one extra `requests` GET per title-relevant result for the real description | `jobspresso.co/?s=...` is plain server-rendered WordPress HTML (WP Job Manager plugin markup, `article.job_listing` per card), no Cloudflare block. A bare `s=Salesforce` is a weak search here for a different reason than Jobright/Indeed/Built In's company-name trap - WordPress's default search matches any word anywhere in the post body, so almost any listing whose JD merely mentions "Salesforce" in passing matches regardless of title (confirmed live: "Senior Financial Analyst", "Customer Operations Manager", etc. all matched a bare query) - so this fans out over `SALESFORCE_TITLES` too. This is a genuinely small site though (10 results/page, single digits of real Salesforce-relevant postings at any time) - the fan-out here is about coverage of whatever phrasing the one or two real listings use, not fighting a large noise problem the way Built In's was. Full JD fetched per title-relevant result only (same pattern as Dice): the search card only has a short summary, but the job's own detail page has the real JD in a `.content-area` div, plain HTML. Posted date is "Month Day" with no year (e.g. "October 20") - a new `parse_month_day` helper in `_dates.py` infers the year from whether that date has happened yet this cycle. No location filtering needed source-side: "Worldwide"/"Anywhere"/blank normalize to bare "Remote" (same convention as Jobgether's "Anywhere"), gates.py's own US-or-remote gate handles the rest. Verified end-to-end: of 222 fetched, only 1 had a Salesforce-relevant title (Salesforce Developer at Chainlink Labs) - genuinely thin current inventory for this source, not a bug (confirmed the whole pipeline works by widening the recency window past that one posting's real age) |
| Monster | **Playwright**, best-effort, single fixed "Salesforce" query (not `SALESFORCE_TITLES`) | added per the user's explicit ask to replicate a sibling local project's own approach, after directly confirming its premise first rather than assuming it: Monster is behind DataDome, a commercial anti-bot service. A real, logged-in browser (the user's own Chrome) passes with *zero* challenge - the block is an automation-fingerprint check (CDP/`navigator.webdriver`), not IP/network-based - but replaying that same real session's cookies through a different HTTP client (our backend's `requests`) still gets a flat 403 with a `captcha-delivery.com` challenge on both the page and the real `search-jobs` API, confirmed live with the user's actual cookies: DataDome ties validity to the connecting client's TLS/JA3 fingerprint (it issues a `mn_ja3` cookie explicitly), not just cookie possession - ruling out a Jobright-style cookie relay here. Plain Playwright with `--disable-blink-features=AutomationControlled` plus a realistic UA/locale/viewport gets past the *page-level* check (confirmed live - no more CAPTCHA page shell) but the underlying `search-jobs` API call is still 403'd every time (confirmed live via network tracing) - the page just renders its own "no jobs found" fallback UI when that happens, indistinguishable from a genuine empty search without inspecting the network tab. This also means the sibling project's own detection heuristic (page body text under 40 characters = blocked) has a blind spot: this failure mode renders a normal-sized page (1300+ characters) that's actually empty boilerplate, not real results - so their check (and this adapter's copy of it) doesn't actually catch it, though the practical effect is the same either way, a title-relevance filter finding zero stub links and returning `[]` cleanly. Net effect, matching the sibling project's own documented experience: this fetches real results only on the rare run DataDome doesn't intervene, and silently returns nothing (no crash, no error) the rest of the time - a deliberate best-effort inclusion, not a reliable source |

**Investigated and not integrated:** The Muse - its public API has no
free-text search and no category matching Salesforce/CRM, and is 400k+ jobs
total, so scanning enough pages to find relevant postings isn't practical the
way it is for the other browse-and-filter sources above (each of those is
only tens-to-low-hundreds of postings total). Obra - its web app is gated
behind **Firebase App Check**, a purpose-built anti-automation service
(distinct from incidental Cloudflare bot-protection): a single real-browser
visit hit a 403 that self-throttled further attempts for 24 hours. That's a
deliberate anti-scraping measure, not something worth working around.
Glassdoor and ZipRecruiter (both formerly JobSpy-backed, removed
2026-09-29) - both now return 0 results via JobSpy, and both are the same
class of problem as Obra, not a query or scraper-code issue: a real
headless browser hitting either site directly gets served a genuine
Cloudflare challenge page ("Humans only" on Glassdoor, "Just a moment..."
on ZipRecruiter, both confirmed live), not the actual search results.
JobSpy's own GitHub tracker independently confirms both are currently
broken upstream too (issue #302 for ZipRecruiter; #347/#350/#384 - three
separate open, unmerged fix attempts - for Glassdoor's specific "400
location not parsed" failure, itself caused by Glassdoor having moved the
static page JobSpy scrapes for a CSRF token, confirmed live: that page now
404s). None of that would be fixed by writing our own scraper the way
Jobgether/Talent.com/Built In were - those needed a real browser or a
different request shape, not a Cloudflare challenge solved out from under
them, which is a different order of problem entirely.

Google Jobs (formerly JobSpy-backed, removed 2026-09-29) - also returning
0 results, but a genuinely different failure mode from the two above: no
Cloudflare wall, a plain request gets a clean 200, JobSpy's scraper just
isn't finding the embedded job-data JSON in the response. Investigation
stalled on a separate, unresolved issue: from this machine, both plain
requests and a real headless browser get geo-redirected to
`google.com.hk` regardless of `hl=en&gl=us` params, so it was never
confirmed whether the real fix is in JobSpy's parsing logic, a
network-routing issue specific to this machine, or both. Removed rather
than left half-working; revisit if that gets disentangled.


**Login-gated sources:** built for Jobright, the first source that actually
benefits from it (its authenticated API returns far more than the ~20-result
anonymous cap, and the anonymous page itself is now Cloudflare-challenged -
see above). This mechanism has flip-flopped once already, worth being
explicit about rather than presenting as if it were always the plan: a
dedicated Playwright profile the user logs into separately → replaced with a
companion Chrome extension using the user's real, already-open Chrome (per
explicit feedback at the time: "it should use whatever Chrome the user
already has open instead") → knowingly reverted back to a dedicated
Playwright profile once the ChatGPT generation engine (below) proved that
exact pattern out and the one real cost - a separate one-time Jobright
sign-in, even if already signed in elsewhere - was re-weighed and accepted
in exchange for dropping the extension as a dependency ("all in the app," no
separate install step). If this flips again, check `git log --
backend/app/jobright_session.py` for the actual current state rather than
trusting this paragraph.

Much narrower in scope than `chatgpt_engine.py`'s browser, since there's no
conversation to have - just detect whether a sign-in is needed, wait for it
if so, then read cookies off the browser context:
- `browser_launch.py` holds the "launch a persistent Chrome context on
  Windows, reattach via CDP to a window a prior run left open, clear a
  locked profile and retry" plumbing - extracted out of `chatgpt_engine.py`
  once this became a second consumer of the exact same logic against a
  different profile directory and CDP port (`data/jobright-profile/`, port
  9334 - distinct from ChatGPT's 9333, so the two profiles stay fully
  independent even if both are mid-flow at once).
- `jobright_browser.py`'s `open_login_flow()` is fire-and-forget: opens the
  dedicated profile on its own short-lived thread (same
  dedicated-thread-with-its-own-`ProactorEventLoop` reasoning as
  `chatgpt_engine.py` - Playwright's async API needs it to launch a browser
  subprocess on Windows, and `uvicorn --reload` forces the wrong loop type
  on the main thread regardless of policy), checks for Jobright's own
  logged-out "Sign In" button (confirmed live against the real page), waits
  for it to clear if present, reads `context.cookies()`, hands the
  `jobright.ai` ones straight to `jobright_session.save_cookies()` - already
  compatible with zero changes, since it expects exactly the
  `[{"name", "value", "domain"}, ...]` shape `context.cookies()` returns -
  then **closes the context**. Unlike ChatGPT's browser (kept open for the
  app's whole lifetime, reused across many separate generation calls),
  Jobright's only needs to exist for the duration of one login flow: grab
  the cookies, close it. The actual fetch afterward is still plain
  `requests` with the saved cookies - no live browser involved in fetching,
  only in obtaining the cookies in the first place.
- `POST /sources/jobright/login` (backend) triggers `open_login_flow()` and
  returns immediately; the frontend finds out the result by polling the
  already-existing `GET /sources/jobright/status` (unchanged: a real live
  request to the authenticated API, not just "were cookies saved" -
  confirmed live that Jobright's API returns a clean, unambiguous signal for
  an invalid/missing session - HTTP 401, `{"success": false, "errorCode":
  41001, "errorMsg": "Cookie not found"}`).

Fetch tab UI/flow: the status badge polls while Jobright is selected and not
yet signed in, so it flips to "signed in" on its own once the user finishes
signing in in the window that opened - no extra click needed. Clicking **Run
Fetch** while not signed in opens that window, shows a notice, and **doesn't
fetch this round** - the next click, now signed in, goes through normally.

The companion extension approach this replaced is described above for
context; `extension/` itself is left in place unused rather than deleted (it
had the user's own in-progress edits at the time of this switch).

**Open question, not yet decided:** whether to keep scraping LinkedIn at all.
A comparable local project (a sibling job-capture tool covering much of this
same source list) deliberately excludes LinkedIn entirely as a matter of
policy, given how aggressively LinkedIn enforces against scraping. This
project currently still includes it via JobSpy.

**Hard gates** (reject, with a stored reason shown in the UI):
- Salesforce relevance (keyword allow-list + negative list, to exclude
  "Account Executive at Salesforce Inc." style false positives). Matches
  against the **title only**, not title+description - originally checked
  both, but that let through a real, common false-positive pattern found
  live on Indeed: a long JD mentioning Salesforce only as a tool the role
  happens to use (e.g. "Healthcare Sales Director" passed because its
  description said "...tracking in Salesforce", despite having nothing to
  do with Salesforce development/administration). Every genuine
  Salesforce-ecosystem role this project targets says so in the title
  itself. Confirmed this wasn't a regression by inspecting what it now
  rejects from Greenhouse specifically (which returns every open job at
  ~55 companies, unfiltered by query, relying entirely on this gate for
  relevance): of 8,886 fetched, only 2 had "Salesforce" in the title, vs.
  1,215 that merely mentioned it somewhere in the description (Client
  Success Lead, Analytics Engineer, etc. - correctly rejected)
- US-located or explicitly Remote-US (location string parsing, not just the
  word "remote" — catches "Remote – India", "Remote (EMEA)")
- Posted within N days (default 7, configurable on the fetch screen)

**Flags** (shown, not rejected): no-sponsorship/citizens-only, C2C/W2-only,
staffing agency, hybrid.

Within-run dedupe: exact (URL/ATS id) and cross-source (hash of
company+normalized title+location).

## Generation engine

Click **Generate** on a `queued` row (single or bulk) → `generating` →
`chatgpt_engine.ask()` drives ChatGPT's real web UI → `generation.py`
parses/validates/renders → `ready`, with a real PDF + JD.txt staged. On any
failure → `failed` + a readable error, retryable (Retry flips it back to
`queued`; click Generate again).

This replaced an earlier sketch (written before any of Fetch/Templates
existed) that assumed a Chrome extension driving ChatGPT, mirroring
Jobright's cookie-relay pattern. Before building either, a sibling desktop
project's own working `chatgpt.py` was studied directly (not copied
blindly - see its own module for the reasoning this pulled from) and its
approach adopted instead, for a concrete reason: an extension-style cookie
relay works for Jobright because its API is a plain HTTP JSON API once you
have valid cookies. ChatGPT isn't a safe bet for that - this project
repeatedly found, investigating other sites, that replaying real session
cookies through a *different* HTTP client than the one that earned them
gets rejected by TLS/device-fingerprint checks (confirmed live against
Monster's DataDome, using the user's own real cookies). Real browser
automation sidesteps that question entirely, and the sibling project
proves it works in practice against chatgpt.com specifically.

**`chatgpt_engine.py`** - a persistent Playwright browser context, not
headless: `launch_persistent_context` against a dedicated Chrome profile
(`data/chatgpt-profile/`, separate from the user's everyday browsing, so a
crash here can't touch it) that the user signs into once, by hand, in the
real visible window that opens - the sign-in is then remembered across
runs. A later run first tries `connect_over_cdp` to reattach to a window a
prior run left open (`--remote-debugging-port=9333`) rather than failing
on the locked profile - this matters more for us than it did for the
sibling project, since `uvicorn --reload` restarts the backend process (and
would otherwise orphan the browser it spawned) on every source save. If the
profile really is locked, Chrome/Edge processes matched by the profile's
own path get force-closed and the `Singleton*` lock files removed before
retrying.

Proven techniques pulled directly from the sibling project's approach:
- **Settle-time completion detection** - "done" means the Stop button is
  gone *and* the answer text hasn't grown for ~2.5s, not just "Stop button
  gone" (that alone would cut a reply off during a streaming pause).
- **Paste-then-verify-length, fall back to chunked typing** - a resume
  prompt (the profile's own prompt.md, placeholders filled in, plus the
  JD) can run to tens of thousands of characters; a long clipboard paste
  into ChatGPT's composer can silently turn into a file attachment instead
  of landing as text, so what actually landed is measured before trusting
  it was sent. The composer is explicitly cleared *before* every paste
  attempt too, not just before the typing fallback - confirmed live as a
  real bug without that: pasting onto a composer that still had leftover
  content from a stale render *added* to it instead of replacing it, which
  is how one prompt ended up sent three times over in a single message.
- **A direct login check, not an inferred one** - whether the user needs
  to sign in is checked by looking for chatgpt.com's own "Log in" button
  directly (`LOGIN_BUTTON`), not by treating "the composer wasn't found"
  as a proxy for "not logged in". The composer-absence approach was tried
  first and confirmed live to be unreliable: `COMPOSER`'s broadest
  fallback selectors (a bare `textarea`, `form textarea`) can match
  something unrelated on the logged-out landing page, so the code would
  think it found the real message box when it hadn't. Nothing is typed or
  pasted into the composer until the login check resolves either way - a
  login prompt never gets a job description silently thrown at it.

`ask()` takes an optional `on_status` callback, called with a short note
when it starts waiting for login. `generation.py` wires this to write
straight into the opportunity's `error` column (guarded to only apply
while the row is still `generating`, in case a late callback fires after
the row's already moved on) - repurposed as a general in-progress status
note, not just a failure message. The Queue screen shows it next to the
`generating` badge in a neutral tone (only real failures get the red
`failed` treatment), so a row waiting on your sign-in says so immediately
instead of sitting silent for up to 5 minutes before finally erroring out.

One deliberate change from the source, though not the only one that ended
up necessary: its sync Playwright API forces a dedicated worker thread +
`queue.Queue` just to serialize access (Playwright's sync API belongs to
one thread for its whole life). The first version of this module used
Playwright's **async API** directly on the main FastAPI event loop under a
single `asyncio.Lock` instead, on the theory that an asyncio-native
backend wouldn't need the sibling's thread. That theory held for
serializing access, but not for the subprocess launch itself: confirmed
live, Playwright's async API launches the browser via a real OS
subprocess, which requires a `ProactorEventLoop` on Windows -
`SelectorEventLoop` raises a bare `NotImplementedError` the instant a
subprocess is requested. `uvicorn --reload` (this project's own dev
launch) makes that unavoidable on the *main* loop specifically: uvicorn's
own source (`uvicorn/loops/asyncio.py`) shows it deliberately instantiates
`SelectorEventLoop` directly whenever `--reload` is active on Windows,
bypassing `asyncio.set_event_loop_policy()` entirely - that fix was tried
first, confirmed live not to work, before landing on the real one:
`chatgpt_engine.py` now runs on its own dedicated thread with its own
directly-instantiated `ProactorEventLoop`, decoupled from whatever the
main FastAPI loop is doing, bridged back via
`run_coroutine_threadsafe`/`asyncio.wrap_future`. New chat per job (not
ChatGPT's Temporary Chat UI toggle) is the context-isolation mechanism, so
one profile's JD/resume can't bleed into the next - simpler, and doesn't
depend on a toggle that's itself a selector-fragile moving target.

**The background worker must never die**, confirmed live as a real gap: an
earlier version had the row lookup outside `run_generation`'s own
try/except, so a failure there (or anything else that broad `except
Exception` didn't catch) could escape and silently kill the whole worker
loop - every opportunity enqueued after that point sat on `generating`
forever, no browser window, no error, and (at the time) no way to act on
it from the UI either. Fixed two ways: the row lookup moved inside the
try, and `_worker_loop` itself now catches broadly around each
`run_generation` call (re-raising `CancelledError` so real shutdown still
works) as a second line of defense, marking the row `failed` and moving on
to the next item regardless of what went wrong. Retry now also accepts a
row in `generating`, not just `failed` - a direct user-facing escape hatch
for a stuck row regardless of cause, on top of the worker no longer being
able to die in the first place.

**`resume_schema.py` + `generation.py`** - ChatGPT is asked to return a
single JSON object instead of a raw HTML document like the sibling
project's own prompt does; validated structurally with Pydantic
(`ResumeJson.model_validate`), not the string-heuristic approach ("starts
with `<html>`, length > 500, no refusal phrases") that project uses for its
free-form output - real schema validation was only possible for us because
Phase 2 already built a real `resume_json` contract and Jinja2 template,
which didn't exist yet when that approach was written.

**`profile.prompt.md` is the single source of truth for both the
tailoring instructions and the exact JSON schema to return** - not
something this project injects. An earlier version of `generation.py`
assumed otherwise (appending its own schema instructions, then
overwriting the LLM's contact fields with the profile's afterward), before
the user corrected it: a real prompt.md already defines its own
placeholder tokens (`{NAME}`, `{LOCATION}`, `{PHONE}`, `{EMAIL}`,
`{LINKEDIN}`, `{JOB_TITLE}`, `{COMPANY}`, `{JD}`) and its own "JSON SCHEMA
- REQUIRED" section. `build_prompt()`'s job is narrower than that first
version assumed: substitute whichever of those tokens are present with
real values *before* sending (`{JD}` is guaranteed to end up in the prompt
either way - substituted in place if present, appended otherwise, so a
simpler prompt.md that doesn't use the convention still gets the job
description at all), then use whatever comes back as-is - no separate
instructions appended, no overwriting the output afterward.

A single in-process background worker (`generation.start_worker()`,
started from `main.py`'s existing startup event) consumes an
`asyncio.Queue` of opportunity ids one at a time - there's only one
browser/conversation anyway. `POST /queue/{id}/generate` (and
`/queue/bulk-generate`) just flip status to `generating` and enqueue,
returning immediately; the Queue screen's existing 5s poll (already built
for the `generating` badge) picks up the eventual `ready`/`failed`
transition, so no new frontend polling logic was needed.

Explicitly not built this pass (see the sibling project for what a fuller
version could look like): an API fallback, and a score/revise follow-up
loop. Both are real YAGNI calls, not oversights - worth adding only if the
web path proves insufficient in practice.

Queue screen actions per row: **Generate** (queued only - kicks off the
pipeline above), **Open Post** (new tab), **Open Folder** (opens the
staging dir via the backend, since browsers can't open local folders),
**Applied** (files the application per "On disk layout" above, appends to
the Sheet, deletes the row), **Remove** (drops the row + staging files,
nothing recorded), **Retry** (failed *or* generating - back to `queued`;
allowed from `generating` too as a manual escape hatch for a stuck row,
regardless of cause).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+ + FastAPI + SQLite (stdlib `sqlite3`) | JobSpy and the ATS scraping ecosystem are Python; FastAPI serves the local UI and exposes an OpenAPI spec for typed frontend clients |
| Frontend | React + Vite + TypeScript + TanStack Query, Tailwind | clean, structured UI without a heavy design system |
| PDF | Jinja2 template → HTML → headless Chromium `page.pdf()` (Playwright) | pixel-accurate, template fully controls layout; the same mechanism renders both Template previews (Phase 2, sample data) and real generations (Phase 3, `resume_json`) |
| ChatGPT / Jobright browsers | Playwright, async API, dedicated persistent browser contexts (`chatgpt_engine.py`, `jobright_browser.py`, sharing launch plumbing via `browser_launch.py`) | drives the real chatgpt.com/jobright.ai web UIs directly, each in its own profile - see "Generation engine" and "Login-gated sources" |
| Sheets | Google Apps Script Web App, bound to the Sheet itself (`docs/apps-script.gs`) | no Cloud project, no service account, no key file - just Extensions > Apps Script inside the Sheet and one Deploy click; see "On-disk layout on Applied" |

## Repo layout

```
liebao-bid-bot/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ db.py                  # sqlite connection + schema (opportunities only)
│  │  ├─ models.py              # pydantic wire models
│  │  ├─ sources/                # one module per source adapter
│  │  ├─ gates.py                # hard filters
│  │  ├─ sheets.py               # Apps Script Web App client (docs/apps-script.gs)
│  │  ├─ profiles.py             # profile CRUD (disk, not SQLite)
│  │  ├─ templates.py            # template CRUD (disk, not SQLite) - independent of profiles
│  │  ├─ resume_schema.py        # ResumeJson Pydantic schema (the LLM output contract)
│  │  ├─ resume_render.py        # jinja2 render + playwright PDF print
│  │  ├─ browser_launch.py       # shared persistent-Chrome-context launch plumbing
│  │  ├─ chatgpt_engine.py       # persistent Playwright context driving chatgpt.com
│  │  ├─ jobright_browser.py     # one-shot Playwright login flow for jobright.ai
│  │  ├─ generation.py           # prompt build, parse/validate, background worker
│  │  └─ routers/
│  │     ├─ fetch.py             # POST /fetch, GET /fetch/export
│  │     ├─ queue.py             # import, list, applied, remove, retry, generate
│  │     ├─ profiles.py
│  │     └─ templates.py         # CRUD + preview.html/preview.pdf
│  ├─ profiles/
│  │  └─ <profile-id>/ profile.json, prompt.md
│  ├─ templates/
│  │  └─ <template-id>/ template.json, template.html
│  └─ pyproject.toml
├─ web/                          # React app
├─ extension/                    # unused - see "Login-gated sources" for why it's kept but unwired
├─ data/                         # gitignored: sqlite db, staging/, browser-sessions/,
│                                 #   chatgpt-profile/, jobright-profile/ (persistent Chrome profiles)
└─ docs/
   └─ ARCHITECTURE.md
```

## Build phases

1. **Fetch** — sources (18 and counting), hard gates + flags, results table,
   XLSX export.
2. **Templates & Queue plumbing** — Profiles and Templates screens (both
   disk-backed CRUD, Templates independent of and live-referenced by
   Profiles), SQLite queue (import, dedupe vs. Sheet, Open Post/Open
   Folder/Applied/Remove/Retry, Sheet append on Applied), the resume
   template/PDF pipeline (`resume_render.py`) exercised via sample-data
   previews since nothing produced real `resume_json` yet.
3. **Generation engine** — `chatgpt_engine.py` + `generation.py`: real
   `resume_json` from ChatGPT's web UI, replacing the sample data Phase 2
   validated the render pipeline against.
4. **Ongoing**: more sources, polish, error handling, revisit API fallback
   if the web path proves insufficient in practice.

Each phase is independently useful and gets its own commit(s).
