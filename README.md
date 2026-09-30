# liebao-bid-bot

Job-application assistant for US/Remote Salesforce roles. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

Status: **Phases 1-3 built.** Fetch screen (18 sources, hard gates, XLSX
export), Queue screen (import shortlist, bulk/single Generate/Applied/
Remove/Retry, Sheet logging), a Profiles screen, a Templates screen (resume
layouts, independent of Profiles - a profile just references one live),
and the generation engine itself: click **Generate** on a queued row and a
real Chrome window (a dedicated profile, separate from your everyday
Chrome) drives chatgpt.com, tailors a resume as JSON against your prompt +
the job description, and prints a real PDF into that row's staging folder
- see docs/ARCHITECTURE.md's "Generation engine" for exactly how. First use
needs a one-time sign-in in that window; it's remembered after that.

## Quick start

Once both are set up once (below), double-click **`start.bat`** at the repo
root — it opens the backend and frontend each in their own console window and
opens `http://127.0.0.1:5173` in your browser (127.0.0.1 rather than
"localhost", since some VPN clients override DNS so "localhost" stops
resolving to loopback). Close either window to stop it.

## Setup

### Backend (Python 3.12 — 3.13/3.14 don't have prebuilt numpy wheels yet for
JobSpy's pin, and there's no C compiler here to build from source)

```
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m playwright install chromium   # needed for the Jobgether source
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```
cd web
npm install
npm run dev -- --host 127.0.0.1
```

### Jobright's full results (optional)

Anonymous access is capped at ~20 results and is currently sometimes
blocked by a Cloudflare challenge Jobright added to its anonymous page.
For the real, authenticated results, select Jobright on the Fetch screen
and click **Run Fetch** — it opens a dedicated sign-in window (a separate
Chrome profile, same idea as the Generate button's ChatGPT window) the
first time; sign in there once and it's remembered after that. See
docs/ARCHITECTURE.md's "Login-gated sources" for how.

### Profiles and Templates

Create profiles from the app's **Profiles** tab (name, contact info, output
folder via the Browse button, Google Sheet tab, which **Template** it uses,
and the resume-tailoring prompt) — nothing here is hand-edited or
hardcoded. Each persists to `backend/profiles/<id>/` on disk (`profile.json`,
`prompt.md`), so the files are there to inspect or back up, just not meant
to be edited by hand.

Templates are managed independently from the **Templates** tab (resume
layout, Jinja2 HTML) and persist to `backend/templates/<id>/`. A profile's
`template_id` is a live reference, not a copy - editing a template changes
what every profile using it renders next. A "Default" template ships out
of the box.

### Google Sheets (optional until you start using Applied)

No Google Cloud project or service account needed - this goes through a
small Apps Script Web App bound to the Sheet itself:

1. Create a Google Sheet, open **Extensions > Apps Script**, and paste in
   `docs/apps-script.gs`. Replace `SECRET` inside it with a long random
   string of your own.
2. **Deploy > New deployment**, type "Web app", Execute as "Me", who has
   access "Anyone with the link" > Deploy. Copy the resulting URL.
3. Put that URL in the profile's **Sheet Web App URL** field, the same
   `SECRET` value in **Sheet secret**, and set **Sheet tab name** to
   whatever tab you want that profile logged to (created automatically on
   first Applied if it doesn't exist).

Without a URL set, import still works (dedupe against the Sheet is just
skipped), but the Applied button will fail until it's set up - and won't
move any files when it does, since the Sheet append is checked first.
