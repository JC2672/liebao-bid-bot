"""Pydantic models shared across routers.

These are the wire types for both the transient fetch-results table (Part 1)
and the persisted `opportunities` queue rows (Part 2). See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RawPosting(BaseModel):
    """One posting as returned by a source adapter, before gating."""

    source: str
    external_id: str
    url: str
    company: str
    title: str
    location: str
    is_remote: bool | None = None
    description: str = ""
    posted_at: datetime | None = None


class GateResult(BaseModel):
    """A posting after gating, ready to show in the fetch results table."""

    source: str
    external_id: str
    url: str
    company: str
    title: str
    location: str
    description: str = ""
    posted_at: datetime | None = None
    passed: bool
    reject_reason: str | None = None
    flags: list[str] = []


class FetchRequest(BaseModel):
    sources: list[str]
    query: str = "Salesforce"
    posted_within_days: int = 7


class FetchResponse(BaseModel):
    results: list[GateResult]
    counts: dict[str, int]


OpportunityStatus = Literal["queued", "generating", "ready", "failed"]


class Opportunity(BaseModel):
    id: int | None = None
    profile: str
    company: str
    title: str
    location: str
    source: str
    url: str
    description: str = ""
    status: OpportunityStatus = "queued"
    error: str | None = None
    resume_json: str | None = None
    staging_dir: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportRequest(BaseModel):
    profile: str
    # Rows come from the uploaded XLSX/CSV; parsed server-side into RawPosting-shaped dicts.


class Profile(BaseModel):
    id: str  # slug, matches the profiles/<id>/ directory name
    name: str  # display name, printed on the resume
    title: str = ""
    location: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    sheet_id: str
    sheet_tab: str
    output_root: str
    template: str = "template.html"
