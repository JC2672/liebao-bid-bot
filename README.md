# liebao-bid-bot

Job-application assistant for US/Remote Salesforce roles. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

Status: **Phase 1** — Fetch screen (10 sources, hard gates, XLSX export),
Queue screen (import shortlist, bulk/single Applied/Remove/Retry, Sheet
logging), and a Profiles screen (create/edit/delete, no hand-edited files)
are wired up. The ChatGPT-web generation engine (Phase 3) is not yet built,
so queued opportunities currently stay at `queued` — there's no PDF pipeline
running against them yet.

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

### Companion Chrome extension (optional, only needed for Jobright's full results)

Load `extension/` unpacked (`chrome://extensions` → Developer mode → Load
unpacked). See `extension/README.md`. Without it, Jobright still works, just
capped at anonymous-only results (~20, and currently sometimes blocked by a
Cloudflare challenge Jobright added to its anonymous page).

### Profiles

Create profiles from the app's **Profiles** tab (name, contact info, output
folder via the Browse button, Google Sheet tab, and the resume-tailoring
prompt) — nothing here is hand-edited or hardcoded. Each still persists to
`backend/profiles/<id>/` on disk (`profile.json`, `prompt.md`, `template.html`,
the last starting as a copy of `profiles/_default_template.html`), so the
files are there to inspect or back up, just not meant to be edited by hand.

### Google Sheets (optional until you start using Applied)

1. Create a Google Cloud service account, download its JSON key to
   `backend/service-account.json` (gitignored).
2. Create a Google Sheet, share it with the service account's email as Editor.
3. Put the Sheet's ID in the profile's **Google Sheet ID** field, and set
   **Sheet tab name** to whatever tab you want that profile logged to
   (created automatically on first Applied if it doesn't exist).

Without this file present, import still works (dedupe against the Sheet is
just skipped), but the Applied button will fail until it's set up.
