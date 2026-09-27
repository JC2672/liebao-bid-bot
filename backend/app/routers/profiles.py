from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import Profile
from ..profiles import get_profile, list_profiles

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[Profile])
def get_all() -> list[Profile]:
    return list_profiles()


@router.get("/{profile_id}", response_model=Profile)
def get_one(profile_id: str) -> Profile:
    try:
        return get_profile(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
