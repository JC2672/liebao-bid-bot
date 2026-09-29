"""Profiles are managed through the UI (create/update/delete), not hand-edited
files - but each still lives on disk at backend/profiles/<id>/ as:
  - profile.json  (structured fields, this module's Profile model)
  - prompt.md      (the tailoring prompt; JD gets appended at generation time)

A profile's resume layout is a *live reference* to a Template (see
templates.py), stored as Profile.template_id - not a file owned by the
profile. Editing that template changes what every profile using it renders
next, with no per-profile template.html to keep in sync.

Profiles are separate identities, not variants of one person - see
docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .models import Profile, ProfileDetail, ProfileInput

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "profile"


def _validate_slug(profile_id: str) -> None:
    if not SLUG_RE.match(profile_id):
        raise ValueError(
            f"Invalid profile id '{profile_id}': use lowercase letters, digits and hyphens only"
        )


def _dir(profile_id: str) -> Path:
    return PROFILES_DIR / profile_id


def list_profiles() -> list[Profile]:
    if not PROFILES_DIR.exists():
        return []
    profiles = []
    for d in sorted(PROFILES_DIR.iterdir()):
        f = d / "profile.json"
        if d.is_dir() and f.exists():
            profiles.append(Profile.model_validate(json.loads(f.read_text(encoding="utf-8"))))
    return profiles


def get_profile(profile_id: str) -> Profile:
    f = _dir(profile_id) / "profile.json"
    if not f.exists():
        raise FileNotFoundError(f"No profile '{profile_id}' at {f}")
    return Profile.model_validate(json.loads(f.read_text(encoding="utf-8")))


def get_detail(profile_id: str) -> ProfileDetail:
    profile = get_profile(profile_id)
    return ProfileDetail(**profile.model_dump(), prompt=get_prompt(profile_id))


def get_prompt(profile_id: str) -> str:
    f = _dir(profile_id) / "prompt.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _write(profile: Profile, prompt: str) -> None:
    d = _dir(profile.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.json").write_text(
        json.dumps(profile.model_dump(), indent=2), encoding="utf-8"
    )
    (d / "prompt.md").write_text(prompt, encoding="utf-8")


def create_profile(data: ProfileInput) -> Profile:
    profile_id = slugify(data.id or data.name)
    _validate_slug(profile_id)
    if _dir(profile_id).exists():
        raise FileExistsError(f"Profile '{profile_id}' already exists")

    profile = Profile(
        id=profile_id, name=data.name, location=data.location,
        phone=data.phone, email=data.email, linkedin=data.linkedin,
        sheet_id=data.sheet_id, sheet_tab=data.sheet_tab, output_root=data.output_root,
        template_id=data.template_id,
    )
    _write(profile, data.prompt)
    return profile


def update_profile(profile_id: str, data: ProfileInput) -> Profile:
    if not _dir(profile_id).exists():
        raise FileNotFoundError(f"No profile '{profile_id}'")
    updated = Profile(
        id=profile_id, name=data.name, location=data.location,
        phone=data.phone, email=data.email, linkedin=data.linkedin,
        sheet_id=data.sheet_id, sheet_tab=data.sheet_tab, output_root=data.output_root,
        template_id=data.template_id,
    )
    _write(updated, data.prompt)
    return updated


def delete_profile(profile_id: str) -> None:
    d = _dir(profile_id)
    if not d.exists():
        raise FileNotFoundError(f"No profile '{profile_id}'")
    shutil.rmtree(d)
