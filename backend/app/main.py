from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from . import generation
from .db import init_db
from .native import pick_folder
from .routers import fetch, fields, jobright_session, profiles, queue, templates

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
app.include_router(fields.router)
app.include_router(jobright_session.router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    # Before the worker starts, not after - a row still `generating` at
    # this exact moment is always a leftover from a previous process that
    # died mid-job (forced-closed browser, server stopped mid-run), never
    # a real in-flight one; see reconcile_interrupted_jobs()'s own
    # docstring for why that's only true right here, at startup.
    generation.reconcile_interrupted_jobs()
    generation.start_worker()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/pick-folder")
def pick_folder_endpoint(description: Annotated[str, Query()] = "Select a folder") -> dict:
    """Opens a native Windows folder-picker dialog and returns the chosen
    path - browsers can't hand back a real filesystem path themselves."""
    return {"path": pick_folder(description)}
