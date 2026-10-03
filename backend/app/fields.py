"""Tech fields (Salesforce, Data Engineering, ...) are managed through the
UI (create/update/delete), the same way Profiles and Templates are - a
Profile just references one by id (Profile.field_id), a live reference,
not a copy: editing a field changes what every profile using it fetches
with next.

Each field lives on disk at backend/fields/<id>/ as a single field.json
(this module's FieldConfig model) - unlike Profiles/Templates there's no
second content file, everything fits in the one JSON. Tracked in git: this
is shared config, not personal data, the same category as
backend/templates/ (unlike backend/profiles/*/, which is gitignored).

See docs/ARCHITECTURE.md's "Fetch: sources & gates" and gates.py's module
docstring for why this exists: every source used to hardcode
Salesforce-specific query/relevance logic directly.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .models import FieldConfig, FieldInput

FIELDS_DIR = Path(__file__).resolve().parent.parent / "fields"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "field"


def _validate_slug(field_id: str) -> None:
    if not SLUG_RE.match(field_id):
        raise ValueError(
            f"Invalid field id '{field_id}': use lowercase letters, digits and hyphens only"
        )


def _dir(field_id: str) -> Path:
    return FIELDS_DIR / field_id


def list_fields() -> list[FieldConfig]:
    if not FIELDS_DIR.exists():
        return []
    fields = []
    for d in sorted(FIELDS_DIR.iterdir()):
        f = d / "field.json"
        if d.is_dir() and f.exists():
            fields.append(FieldConfig.model_validate(json.loads(f.read_text(encoding="utf-8"))))
    return fields


def get_field(field_id: str) -> FieldConfig:
    f = _dir(field_id) / "field.json"
    if not f.exists():
        raise FileNotFoundError(f"No field '{field_id}' at {f}")
    return FieldConfig.model_validate(json.loads(f.read_text(encoding="utf-8")))


def _write(field: FieldConfig) -> None:
    d = _dir(field.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "field.json").write_text(json.dumps(field.model_dump(), indent=2), encoding="utf-8")


def create_field(data: FieldInput) -> FieldConfig:
    field_id = slugify(data.id or data.name)
    _validate_slug(field_id)
    if _dir(field_id).exists():
        raise FileExistsError(f"Field '{field_id}' already exists")
    field = FieldConfig(
        id=field_id, name=data.name, query_term=data.query_term,
        title_list=data.title_list, relevance_allow=data.relevance_allow,
        relevance_deny=data.relevance_deny,
    )
    _write(field)
    return field


def update_field(field_id: str, data: FieldInput) -> FieldConfig:
    if not _dir(field_id).exists():
        raise FileNotFoundError(f"No field '{field_id}'")
    field = FieldConfig(
        id=field_id, name=data.name, query_term=data.query_term,
        title_list=data.title_list, relevance_allow=data.relevance_allow,
        relevance_deny=data.relevance_deny,
    )
    _write(field)
    return field


def delete_field(field_id: str) -> None:
    d = _dir(field_id)
    if not d.exists():
        raise FileNotFoundError(f"No field '{field_id}'")
    shutil.rmtree(d)
