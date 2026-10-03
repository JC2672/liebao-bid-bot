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
    # The profile id, not free text - its field (query term/title list/
    # relevance keywords) and country drive every source's query now. See
    # routers/fetch.py's module docstring for why the old free-text query
    # box was removed.
    profile: str
    posted_within_days: int = 7


class FetchResponse(BaseModel):
    results: list[GateResult]
    counts: dict[str, int]


SourceFetchStatus = Literal["pending", "running", "done", "failed"]


class SourceProgress(BaseModel):
    """One source's live state within a running fetch job - see
    routers/fetch.py's module docstring for why this exists (a real,
    literal checklist on the Fetch tab, not a decorative animation)."""

    name: str
    status: SourceFetchStatus = "pending"
    # Raw postings this source returned, before dedupe/gating - set once
    # `status` is "done"; stays None for "pending"/"running"/"failed"
    # (a failed source never produced a real count).
    count: int | None = None


class FetchStatusResponse(BaseModel):
    running: bool
    sources: list[SourceProgress]
    result: FetchResponse | None = None
    error: str | None = None


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
    # A live reference to fields/<field_id>/ (same pattern as template_id) -
    # which query term/title list/relevance keywords a fetch for this
    # profile uses. See fields.py.
    field_id: str = "salesforce"
    # Where this profile is looking for work - independent of `field_id`
    # (geography and tech domain are separate axes). Drives gates.py's
    # is_located_or_remote_in(), whose *shape* ("located in this country OR
    # explicitly remote-for-it") stays fixed; this is the only part of it
    # that varies.
    country: str = "United States"


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
    field_id: str = "salesforce"
    country: str = "United States"
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


class FieldConfig(BaseModel):
    """A tech field's own fetch behavior - what a Profile.field_id points
    at. Generalizes what used to be hardcoded Salesforce-only logic
    scattered across gates.py and several source modules; see
    docs/ARCHITECTURE.md's "Fetch: sources & gates" and gates.py's module
    docstring for the full reasoning."""

    id: str  # slug, matches the fields/<id>/ directory name
    name: str  # display name, shown in the Setup > Fetch options tab and Profile's picker
    query_term: str  # for sources that take the caller's free text as-is
    title_list: list[str] = []  # for sources where a bare query_term is a trap - fanned out instead
    relevance_allow: list[str] = []  # a posting's title must match one of these
    relevance_deny: list[str] = []  # ...and must not match any of these


class FieldInput(BaseModel):
    """Body for creating/updating a field from the UI. `id` is only read on
    create (path param is authoritative on update) and must be a
    filesystem-safe slug: lowercase letters, digits, hyphens."""

    id: str = ""
    name: str
    query_term: str
    title_list: list[str] = []
    relevance_allow: list[str] = []
    relevance_deny: list[str] = []
