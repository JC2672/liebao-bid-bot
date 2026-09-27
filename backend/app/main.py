from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import fetch, profiles, queue

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


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"ok": True}
