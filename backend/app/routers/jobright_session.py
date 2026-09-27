from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import jobright_session as session

router = APIRouter(prefix="/sources/jobright", tags=["jobright-session"])


@router.get("/status")
def get_status() -> dict:
    return {
        "logged_in": session.check_session(),
        "login_in_progress": session.login_in_progress(),
    }


@router.post("/login/start")
def login_start() -> dict:
    session.start_login()
    return {"ok": True}


@router.post("/login/finish")
def login_finish() -> dict:
    logged_in = session.finish_login()
    if not logged_in:
        raise HTTPException(
            400,
            "No active login to finish, or the saved session doesn't look "
            "valid - make sure you completed sign-in in the opened window.",
        )
    return {"ok": True, "logged_in": True}


@router.post("/login/cancel")
def login_cancel() -> dict:
    session.cancel_login()
    return {"ok": True}
