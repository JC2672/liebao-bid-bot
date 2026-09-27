"""Load per-profile config from backend/profiles/<name>/profile.json.

Each profile directory also holds prompt.md (the tailoring prompt, JD gets
appended at generation time) and a template.html (resume layout). Profiles
are separate identities - see docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Profile

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


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
    f = PROFILES_DIR / profile_id / "profile.json"
    if not f.exists():
        raise FileNotFoundError(f"No profile '{profile_id}' at {f}")
    return Profile.model_validate(json.loads(f.read_text(encoding="utf-8")))


def get_prompt(profile_id: str) -> str:
    f = PROFILES_DIR / profile_id / "prompt.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def get_template_path(profile: Profile) -> Path:
    return PROFILES_DIR / profile.id / profile.template
