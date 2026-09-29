from __future__ import annotations

import asyncio
import sys
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from . import generation
from .db import init_db
from .native import pick_folder
from .routers import fetch, jobright_session, profiles, queue, templates

# Playwright's async API launches the browser via a real OS subprocess,
# which asyncio's SelectorEventLoop cannot do on Windows at all - it raises
# a bare `NotImplementedError` with no other detail the moment a subprocess
# is requested, which is exactly what a Generate click hit live (confirmed
# with the user: no Chrome window ever opened, just this error on all three
# rows). `--reload` (see start.bat) is the trigger: its reload subprocess
# doesn't inherit Python 3.8+'s own Proactor-by-default policy on Windows,
# so this has to be forced explicitly, as early as possible in the actual
# worker process uvicorn --reload restarts on every file save.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="liebao-bid-bot")

app.add_middleware(
    CORSMiddleware,
    # Both hostnames are allowed since some VPN clients override DNS such that
    # "localhost" no longer resolves to loopback - see start.bat.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fetch.router)
app.include_router(queue.router)
app.include_router(profiles.router)
app.include_router(templates.router)
app.include_router(jobright_session.router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    generation.start_worker()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/pick-folder")
def pick_folder_endpoint(description: Annotated[str, Query()] = "Select a folder") -> dict:
    """Opens a native Windows folder-picker dialog and returns the chosen
    path - browsers can't hand back a real filesystem path themselves."""
    return {"path": pick_folder(description)}
