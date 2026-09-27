from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import profiles as profiles_module
from ..db import get_conn
from ..models import Profile, ProfileDetail, ProfileInput

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
def list_all() -> list[Profile]:
    return profiles_module.list_profiles()


@router.get("/{profile_id}")
def get_one(profile_id: str) -> ProfileDetail:
    try:
        return profiles_module.get_detail(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("")
def create(data: ProfileInput) -> Profile:
    try:
        return profiles_module.create_profile(data)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{profile_id}")
def update(profile_id: str, data: ProfileInput) -> Profile:
    try:
        return profiles_module.update_profile(profile_id, data)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{profile_id}")
def delete(profile_id: str) -> dict:
    with get_conn() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE profile = ?", (profile_id,)
        ).fetchone()
    if count:
        raise HTTPException(
            409,
            f"Profile '{profile_id}' still has {count} opportunity(ies) in its queue. "
            "Remove or apply them first.",
        )
    try:
        profiles_module.delete_profile(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}
