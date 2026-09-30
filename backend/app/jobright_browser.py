"""One-shot Jobright login via a dedicated Playwright browser profile -
replaces the companion Chrome extension's cookie relay (see
docs/ARCHITECTURE.md's "Login-gated sources" section for the history: this
exact approach was tried once before, replaced with the extension per
explicit feedback at the time, then knowingly reverted back to this after
the ChatGPT generation engine proved the pattern out and its cost - one
separate sign-in, even if already signed into Jobright elsewhere - was
re-weighed and accepted).

Much smaller in scope than chatgpt_engine.py: no conversation to have, so
no composer/paste/send/reply-wait machinery - just open the browser,
detect whether a sign-in is needed, wait for it if so, then read cookies
off the context and save them via jobright_session.save_cookies() (already
compatible with zero changes - it expects exactly the
`[{"name", "value", "domain"}, ...]` shape `context.cookies()` returns).

Also unlike chatgpt_engine.py's browser, which is kept open for the app's
whole lifetime and reused across many separate generation calls, this one
only needs to exist for the duration of one login flow: grab the cookies,
close it. jobright_source.py's actual fetch continues to use plain
`requests` with the saved cookies - no live browser involved in fetching,
only in obtaining the cookies in the first place. Its own dedicated
profile (`data/jobright-profile/`) and CDP port (9334) are kept separate
from ChatGPT's, so the two stay fully independent.

Still needs the same dedicated-thread-with-its-own-ProactorEventLoop
pattern as chatgpt_engine.py, for the same reason (see that module's
docstring): Playwright's async API requires it to launch a browser
subprocess on Windows, and `uvicorn --reload` forces the wrong loop type
on the main thread regardless of policy. Unlike chatgpt_engine.py's
long-lived worker thread, this one is short-lived - it starts fresh for
each login attempt and ends once that attempt finishes.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright

from . import browser_launch
from . import jobright_session

StatusCallback = Callable[[str], None] | None

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
USER_DATA = DATA_DIR / "jobright-profile"

# Distinct from chatgpt_engine.py's 9333, so the two dedicated profiles
# never collide even if both happen to be mid-flow at once.
CDP_PORT = 9334

LOGIN_WAIT = 300  # seconds - same budget as ChatGPT's, may mean typing a password

# Confirmed live against the real logged-out page (2026-09-29): the header
# shows a "SIGN IN" button with this class when not signed in. Kept as a
# short list, same defensive pattern as chatgpt_engine.LOGIN_BUTTON, since
# Jobright's markup can change just as ChatGPT's does.
SIGN_IN_BUTTON = ["button:has-text('Sign In')", "[class*='sign-in-button']"]


class LoginError(Exception):
    """Something the user can act on."""


_busy = threading.Lock()


def open_login_flow(on_status: StatusCallback = None) -> bool:
    """Fire-and-forget: starts a dedicated thread that opens the Jobright
    profile, waits for sign-in if needed, and saves cookies on success.
    Returns True if a flow was actually started, False if one was already
    running (a double-click, say) - the caller doesn't need to await
    anything, since the frontend finds out the result by polling
    GET /sources/jobright/status same as it already does."""
    if not _busy.acquire(blocking=False):
        return False

    def _runner() -> None:
        try:
            loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_login_flow(on_status))
            finally:
                loop.close()
        except LoginError as exc:
            print(f"[jobright_browser] login flow failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - fire-and-forget; never let this thread die loudly
            print(f"[jobright_browser] login flow raised an unexpected error: {exc}")
        finally:
            _busy.release()

    threading.Thread(target=_runner, daemon=True).start()
    return True


def _report(on_status: StatusCallback, message: str) -> None:
    if on_status is None:
        return
    try:
        on_status(message)
    except Exception:  # noqa: BLE001 - a broken status callback shouldn't break the login flow
        pass


async def _login_flow(on_status: StatusCallback) -> None:
    async with async_playwright() as pw:
        try:
            context, page = await browser_launch.open_persistent_context(pw, USER_DATA, CDP_PORT)
        except browser_launch.LaunchError as exc:
            raise LoginError(str(exc)) from exc

        try:
            await page.goto("https://jobright.ai/", wait_until="domcontentloaded", timeout=60000)

            if await browser_launch.visible(page, SIGN_IN_BUTTON):
                _report(on_status, "Waiting for you to sign in to Jobright - check the browser window that opened.")
                deadline = time.time() + LOGIN_WAIT
                signed_in = False
                while time.time() < deadline:
                    if not await browser_launch.visible(page, SIGN_IN_BUTTON):
                        signed_in = True
                        break
                    await asyncio.sleep(1)
                if not signed_in:
                    raise LoginError(
                        f"No Jobright sign-in was detected within {LOGIN_WAIT} seconds. "
                        "Sign in in the window that opened, then try again."
                    )

            cookies = await context.cookies()
            jobright_cookies = [c for c in cookies if "jobright.ai" in c.get("domain", "")]
            jobright_session.save_cookies(jobright_cookies)

            # check_session() makes a real blocking `requests` call - fine to
            # do once here, but off the event loop like generation.py already
            # does for its own blocking Playwright/requests calls.
            if not await asyncio.to_thread(jobright_session.check_session):
                raise LoginError(
                    "Signed in, but the saved Jobright session doesn't look "
                    "valid yet - try again."
                )
            _report(on_status, "Signed in to Jobright.")
        finally:
            await context.close()
