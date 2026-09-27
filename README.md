# liebao-bid-bot

Job-application assistant for US/Remote Salesforce roles. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

Status: **Phase 1** — Fetch screen (sources + hard gates + XLSX export) and
Queue screen (import shortlist, Applied/Remove/Retry, Sheet logging) are wired
up. The ChatGPT-web generation engine (Phase 3) is not yet built, so queued
opportunities currently stay at `queued` — there's no PDF pipeline running
against them yet.

## Setup

### Backend (Python 3.12 — 3.13/3.14 don't have prebuilt numpy wheels yet for
JobSpy's pin, and there's no C compiler here to build from source)

```
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m playwright install chromium   # needed once Phase 2's PDF rendering lands
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload
```

### Frontend

```
cd web
npm install
npm run dev   # http://localhost:5173
```

### Profiles

Copy `backend/profiles/example/` to a new folder per real identity
(`backend/profiles/<your-slug>/`) and fill in `profile.json`, `prompt.md`
(your real tailoring prompt), and `template.html` (or leave the placeholder
template for now).

### Google Sheets (optional until you start using Applied)

1. Create a Google Cloud service account, download its JSON key to
   `backend/service-account.json` (gitignored).
2. Create a Google Sheet, share it with the service account's email as Editor.
3. Put the Sheet's ID in each profile's `profile.json` under `sheet_id`, and
   set `sheet_tab` to whatever tab name you want that profile logged to
   (created automatically on first Applied if it doesn't exist).

Without this file present, import still works (dedupe against the Sheet is
just skipped), but the Applied button will fail until it's set up.
