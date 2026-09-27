from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import jobright_session as session

router = APIRouter(prefix="/sources/jobright", tags=["jobright-session"])


class CookiePayload(BaseModel):
    name: str
    value: str
    domain: str = ""


class CookiesRequest(BaseModel):
    cookies: list[CookiePayload]


@router.get("/status")
def get_status() -> dict:
    return {"logged_in": session.check_session()}


@router.post("/cookies")
def receive_cookies(body: CookiesRequest) -> dict:
    """Called by the companion Chrome extension after reading the user's
    real jobright.ai cookies from their own browser."""
    session.save_cookies([c.model_dump() for c in body.cookies])
    return {"logged_in": session.check_session()}
