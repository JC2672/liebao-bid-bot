from __future__ import annotations

from fastapi import APIRouter

from .. import jobright_browser
from .. import jobright_session as session

router = APIRouter(prefix="/sources/jobright", tags=["jobright-session"])


@router.get("/status")
def get_status() -> dict:
    return {"logged_in": session.check_session()}


@router.post("/login")
def start_login() -> dict:
    """Opens the dedicated Jobright browser profile and, if needed, waits
    for the user to sign in - fire-and-forget, same pattern as Generate:
    the frontend finds out the result by polling GET /status, not from
    this response."""
    started = jobright_browser.open_login_flow()
    return {"started": started}
