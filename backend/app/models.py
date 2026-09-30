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


class BulkIds(BaseModel):
    ids: list[int]


class ImportRequest(BaseModel):
    profile: str
    # Rows come from the uploaded XLSX/CSV; parsed server-side into RawPosting-shaped dicts.


class Profile(BaseModel):
    id: str  # slug, matches the profiles/<id>/ directory name
    name: str  # display name, printed on the resume
    location: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    # Applied tracking goes through a Google Apps Script Web App bound to
    # the profile's Sheet, not a service account - see sheets.py's module
    # docstring. `sheet_secret` is checked by that script so a leaked URL
    # alone can't be used to write rows into someone's sheet.
    sheet_webapp_url: str = ""
    sheet_secret: str = ""
    sheet_tab: str
    output_root: str
    # A live reference to templates/<template_id>/, not a per-profile copy -
    # editing that template changes what every profile using it renders next,
    # with no per-profile file to keep in sync. See templates.py.
    template_id: str = "default"


class ProfileDetail(Profile):
    """Profile plus its prompt text, for the edit form. GET-only shape."""

    prompt: str = ""


class ProfileInput(BaseModel):
    """Body for creating/updating a profile from the UI. `id` is only read on
    create (path param is authoritative on update) and must be a filesystem-
    safe slug: lowercase letters, digits, hyphens."""

    id: str = ""
    name: str
    location: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    sheet_webapp_url: str = ""
    sheet_secret: str = ""
    sheet_tab: str
    output_root: str
    template_id: str = "default"
    prompt: str = ""


class Template(BaseModel):
    id: str  # slug, matches the templates/<id>/ directory name
    name: str  # display name, shown in the Templates tab and Profile's picker


class TemplateDetail(Template):
    """Template plus its raw Jinja2 HTML source, for the edit form. GET-only shape."""

    html: str = ""


class TemplateInput(BaseModel):
    """Body for creating/updating a template from the UI. `id` is only read
    on create (path param is authoritative on update) and must be a
    filesystem-safe slug: lowercase letters, digits, hyphens."""

    id: str = ""
    name: str
    html: str
