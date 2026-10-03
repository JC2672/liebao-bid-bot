from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import fields as fields_module
from .. import profiles as profiles_module
from ..models import FieldConfig, FieldInput

router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("")
def list_all() -> list[FieldConfig]:
    return fields_module.list_fields()


@router.get("/{field_id}")
def get_one(field_id: str) -> FieldConfig:
    try:
        return fields_module.get_field(field_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("")
def create(data: FieldInput) -> FieldConfig:
    try:
        return fields_module.create_field(data)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/{field_id}")
def update(field_id: str, data: FieldInput) -> FieldConfig:
    try:
        return fields_module.update_field(field_id, data)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{field_id}")
def delete(field_id: str) -> dict:
    using = [p.name for p in profiles_module.list_profiles() if p.field_id == field_id]
    if using:
        raise HTTPException(
            409,
            f"Field '{field_id}' is still used by profile(s): {', '.join(using)}. "
            "Switch them to a different field first.",
        )
    try:
        fields_module.delete_field(field_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}
