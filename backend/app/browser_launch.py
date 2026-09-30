"""Shared "launch a persistent Chrome context on Windows" plumbing.

Extracted out of chatgpt_engine.py once a second consumer (jobright_browser.py)
needed the exact same launch/reattach/recovery logic against a different
profile directory and CDP port - this is a mechanical extraction, not a
behavior change; see chatgpt_engine.py's module docstring for the full
reasoning behind persistent profiles, CDP reattachment, and orphan cleanup
that this module implements generically.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright


class LaunchError(Exception):
    """Something the user can act on."""


async def open_persistent_context(
    play: Playwright, user_data: Path, cdp_port: int
) -> tuple[BrowserContext, Page]:
    """A Chrome window against the given persistent profile, reattaching to
    a window a prior run left open (via CDP on `cdp_port`) rather than
    fighting it, and clearing a locked profile before a retry if needed."""
    user_data.mkdir(parents=True, exist_ok=True)

    reconnected = await _reconnect(play, cdp_port)
    if reconnected is not None:
        context, page = reconnected
        page.set_default_timeout(30000)
        return context, page

    context, failures = None, []
    for attempt in (1, 2):
        round_errors = []
        for channel in ("chrome", "msedge", None):
            try:
                context = await _launch(play, user_data, cdp_port, channel)
                break
            except Exception as exc:  # noqa: BLE001 - tried across channels below
                round_errors.append(exc)
                context = None
        if context is not None:
            break
        failures = round_errors
        # A locked profile is the usual first failure, and clearing it is
        # exactly what lets the second attempt through.
        if attempt == 1 and any(_locked(e) for e in round_errors):
            _close_orphans(user_data)
        else:
            break

    if context is None:
        raise LaunchError(_why(failures))

    page = context.pages[0] if context.pages else await context.new_page()
    page.set_default_timeout(30000)
    return context, page


async def _reconnect(play: Playwright, cdp_port: int) -> tuple[BrowserContext, Page] | None:
    """Reuse a window a prior run left open, rather than fighting it -
    important here since `uvicorn --reload` restarts the backend process
    (and would otherwise re-launch a new Chrome, leaving the old one
    orphaned and the profile locked) on every source file save."""
    try:
        browser: Browser = await play.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}", timeout=4000)
    except Exception:  # noqa: BLE001 - no window to reattach to, fall through to a fresh launch
        return None

    try:
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        return context, page
    except Exception:  # noqa: BLE001 - reattach failed; a fresh launch is the fallback
        try:
            await browser.close()
        except Exception:  # noqa: BLE001 - already gone
            pass
        return None


async def _launch(play: Playwright, user_data: Path, cdp_port: int, channel: str | None) -> BrowserContext:
    return await play.chromium.launch_persistent_context(
        str(user_data), headless=False, channel=channel, viewport=None,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            f"--remote-debugging-port={cdp_port}",
        ],
    )


def _locked(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "already in use" in text or "existing browser session" in text or "singletonlock" in text


def _close_orphans(user_data: Path) -> None:
    """Shut any browser still holding this profile.

    Matched on the profile path, so only windows this project started are
    touched - an everyday Chrome session is never disturbed. A blocking
    subprocess call, accepted here since this only runs on the rare
    profile-locked recovery path, not on every request.
    """
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or "
        "Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*%s*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        % str(user_data).replace("'", "''")
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:  # noqa: BLE001 - best-effort cleanup only
        pass

    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            os.remove(user_data / name)
        except OSError:
            pass


def _why(failures: list[Exception]) -> str:
    if any(_locked(e) for e in failures):
        return (
            "A browser window from an earlier run is still holding the "
            "profile, and it could not be closed automatically. Close "
            "every Chrome window this project opened, then try again."
        )
    ranked = [e for e in failures if "Executable doesn't exist" not in str(e)] or failures
    text = str(ranked[0]) if ranked else "unknown error"
    if "Executable doesn't exist" in text or "playwright install" in text:
        return (
            "No usable browser. Install Google Chrome, or get Playwright's "
            "own with:\n\n    python -m playwright install chromium"
        )
    return f"Could not start a browser:\n\n{text[:300]}"


# ── Finding/checking elements ─────────────────────────────────────────────


async def find(page: Page, selectors: list[str], timeout: int = 8000) -> Locator | None:
    """First selector that's actually on the page.

    Sites rename things, so each selector gets a short look before the next
    is tried, and only the last round is given the full wait - otherwise a
    name that no longer exists burns the whole budget before the one that
    works is even reached.
    """
    quick = min(1200, timeout)
    for round_timeout in (quick, timeout):
        for selector in selectors:
            try:
                found = page.locator(selector).first
                await found.wait_for(state="visible", timeout=round_timeout)
                return found
            except Exception:  # noqa: BLE001 - try the next selector/round
                continue
        if round_timeout >= timeout:
            break
    return None


async def visible(page: Page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            if await page.locator(selector).first.is_visible(timeout=400):
                return True
        except Exception:  # noqa: BLE001 - try the next selector
            continue
    return False
