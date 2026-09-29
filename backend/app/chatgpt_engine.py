"""Drives ChatGPT's real web UI via a persistent Playwright browser context -
not the paid API, and not a companion-extension cookie relay like Jobright's.

Adapted from a sibling desktop project's proven `chatgpt.py` (studied, not
copied blindly - see docs/ARCHITECTURE.md's "Generation engine" section for
the full reasoning).

Why real browser automation, not a cookie relay: this project repeatedly
found, investigating other sites this session, that replaying real session
cookies through a *different* HTTP client (our backend's `requests`, not
the browser that earned them) gets rejected by TLS/device-fingerprint
checks - confirmed live against Monster's DataDome using the user's own
real cookies. ChatGPT is exactly the kind of target that could have the
same defense. Driving the actual browser sidesteps the question entirely.

Why a dedicated persistent profile, not the user's everyday Chrome (unlike
Jobright's extension, which deliberately uses the user's *already-open*
browser): this needs to actively type/paste/read a page over a
minutes-long interaction, not just borrow a cookie in passing. A separate
profile also means a crash here can't disturb the user's real browsing
session, and reattaching to it via `connect_over_cdp` (see `_open` below)
means the login is only ever needed once.

Why a dedicated background thread with its own event loop, when the rest of
this project just awaits things on FastAPI's own loop: confirmed live,
this is not optional on Windows. Playwright's async API launches the
browser via a real OS subprocess (`asyncio.create_subprocess_exec`), which
requires a `ProactorEventLoop` on Windows - `SelectorEventLoop` raises a
bare `NotImplementedError` the instant a subprocess is requested, with no
other detail. `uvicorn --reload` (this project's own dev launch, see
start.bat) makes this unavoidable on the *main* loop specifically: reading
uvicorn's own source (`uvicorn/loops/asyncio.py`) shows it deliberately
instantiates `SelectorEventLoop` directly whenever `--reload` is active on
Windows (needed for its reload-supervisor's own signal handling), bypassing
`asyncio.set_event_loop_policy()` entirely - that fix was tried first here,
confirmed live not to work, before landing on this one. A sibling desktop
project never hits this at all, not because it solved something harder,
but because it's a standalone app with no ASGI reload server in the
picture. Running Playwright on its own thread, with its own directly-
instantiated `ProactorEventLoop` (bypassing the policy question entirely,
not just working around uvicorn's override of it), decouples the two
completely - this works the same whether or not `--reload` is on.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pyperclip
from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
USER_DATA = DATA_DIR / "chatgpt-profile"
CHAT_URL = "https://chatgpt.com/"

# Chrome listens here so a later run can reattach to a window a prior run
# left open, instead of failing on the locked profile - matters more for
# us than it did for the sibling project, since `uvicorn --reload` restarts
# the Python process on every file save without ever closing the browser it
# spawned. Not 9222, which an everyday debugging session might be using.
CDP_PORT = 9333

# Waits, in seconds.
LOGIN_WAIT = 300   # long, because it may mean typing a password
REPLY_WAIT = 600   # a long resume can stream for minutes
SETTLE = 2.5       # text must stop growing for this long to count as done
SILENT_WAIT = 90   # nothing readable by now means it cannot be read

# The composer, the send/stop buttons, and the replies. Several selectors
# each: ChatGPT's markup changes, and an old one often survives alongside
# the new.
COMPOSER = ["div[contenteditable='true']", "#prompt-textarea", "textarea[data-id]", "form textarea", "textarea"]
SEND = ["button[aria-label*='Send']", "[data-testid='send-button']",
        "button[data-testid='fruitjuice-send-button']", "button[type='submit']"]
STOP = ["button[aria-label*='Stop']", "[data-testid='stop-button']", "button[aria-label*='stop']"]

# Read in the page, because the reply body is a sibling of the element that
# marks the turn as the assistant's, not its parent - no single CSS
# selector reaches it. Several generations of ChatGPT markup tried in turn.
# Our prompt asks for a JSON object in a fenced code block, so - like the
# sibling project's HTML case - the longest <pre><code> block is preferred
# over the surrounding chat prose.
_READ_ANSWER = """() => {
  const inUser = (el) => !!(el.closest &&
      (el.closest('[data-user-message-bubble]') ||
       el.closest('[data-message-author-role="user"]')));

  let bodies = [...document.querySelectorAll(
      '[data-markdown-text-style], [class*="MarkdownRoot"], .markdown,' +
      ' [data-message-author-role="assistant"]')].filter(e => !inUser(e));

  if (!bodies.length) {
    const marks = [...document.querySelectorAll(
        '[data-conversation-role="assistant"], [data-chatgpt-agent-turn-start]')];
    const last = marks[marks.length - 1];
    if (last && last.nextElementSibling) bodies = [last.nextElementSibling];
  }

  const el = bodies[bodies.length - 1];
  if (!el) return '';

  const code = [...el.querySelectorAll('pre code, pre')]
      .map(p => (p.innerText || '').trim()).filter(Boolean);
  if (code.length) return code.sort((a, b) => b.length - a.length)[0];

  return (el.innerText || '').trim();
}"""


class ChatError(Exception):
    """Something the user can act on."""


_playwright: Playwright | None = None
_context: BrowserContext | None = None
_page: Page | None = None
_lock: asyncio.Lock | None = None  # created on the dedicated thread, see _thread_main

_thread: threading.Thread | None = None
_thread_loop: asyncio.AbstractEventLoop | None = None
_thread_ready = threading.Event()


def _thread_main() -> None:
    """Owns Playwright for its whole life, on a loop capable of launching a
    subprocess on Windows regardless of what the main FastAPI loop is -
    see the module docstring."""
    global _thread_loop, _lock
    _thread_loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
    asyncio.set_event_loop(_thread_loop)
    _lock = asyncio.Lock()
    _thread_ready.set()
    _thread_loop.run_forever()


def _ensure_thread() -> asyncio.AbstractEventLoop:
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread_ready.clear()
        _thread = threading.Thread(target=_thread_main, daemon=True)
        _thread.start()
        _thread_ready.wait(timeout=10)
    assert _thread_loop is not None
    return _thread_loop


async def ask(prompt: str, new_chat: bool = True) -> str:
    """Send one prompt, return ChatGPT's reply text.

    Runs on the dedicated Playwright thread (see module docstring for why),
    bridged back into the caller's own event loop via
    `run_coroutine_threadsafe`. Only one call runs at a time on that thread
    (there's only one browser, one conversation) - concurrent callers
    simply wait their turn. `new_chat=False` would continue the chat
    already open (not used by this project yet, but kept since a follow-up
    like job_finder's score/revise loop is a plausible later addition).
    """
    loop = _ensure_thread()
    future = asyncio.run_coroutine_threadsafe(_ask_on_thread(prompt, new_chat), loop)
    return await asyncio.wrap_future(future)


async def _ask_on_thread(prompt: str, new_chat: bool) -> str:
    assert _lock is not None
    async with _lock:
        return await _converse(prompt, new_chat)


async def _converse(prompt: str, new_chat: bool) -> str:
    global _context, _page
    try:
        if _context is None or not _context.pages:
            _context, _page = await _open()
            new_chat = True  # a fresh window has no chat to follow on
        page = _page
        assert page is not None

        if new_chat:
            # A fresh chat per job, so one opportunity's JD/resume can't
            # bleed into the next - simpler than relying on ChatGPT's own
            # Temporary Chat toggle, which is itself a moving UI target.
            await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)

        box = await _find(page, COMPOSER, timeout=15000)
        if box is None:
            box = await _wait_for_login(page)

        await box.click()
        await _fill(page, prompt)

        send = await _find(page, SEND, timeout=4000)
        if send is not None:
            await send.click()
        else:
            await page.keyboard.press("Enter")

        return await _await_reply(page)
    except ChatError:
        raise
    except Exception as exc:
        # A broken page isn't worth keeping; the next call reopens it.
        _context = _page = None
        raise ChatError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc


async def _wait_for_login(page: Page) -> Locator:
    deadline = time.time() + LOGIN_WAIT
    while time.time() < deadline:
        box = await _find(page, COMPOSER, timeout=3000)
        if box is not None:
            return box
    raise ChatError(
        "No ChatGPT message box appeared. Sign in to chatgpt.com in the "
        "window that opened, then click Generate again - the sign-in is "
        "remembered after that."
    )


# ── Opening the browser ────────────────────────────────────────────────


async def _open() -> tuple[BrowserContext, Page]:
    """A Chrome window signed into ChatGPT, reusing the saved profile."""
    global _playwright
    USER_DATA.mkdir(parents=True, exist_ok=True)
    if _playwright is None:
        _playwright = await async_playwright().start()

    reconnected = await _reconnect(_playwright)
    if reconnected is not None:
        context, page = reconnected
        page.set_default_timeout(30000)
        return context, page

    context, failures = None, []
    for attempt in (1, 2):
        round_errors = []
        for channel in ("chrome", "msedge", None):
            try:
                context = await _launch(_playwright, channel)
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
            _close_orphans()
        else:
            break

    if context is None:
        raise ChatError(_why(failures))

    page = context.pages[0] if context.pages else await context.new_page()
    page.set_default_timeout(30000)
    return context, page


async def _reconnect(play: Playwright) -> tuple[BrowserContext, Page] | None:
    """Reuse a window a prior run left open, rather than fighting it -
    important here since `uvicorn --reload` restarts the backend process
    (and would otherwise re-launch a new Chrome, leaving the old one
    orphaned and the profile locked) on every source file save."""
    try:
        browser: Browser = await play.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}", timeout=4000)
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


async def _launch(play: Playwright, channel: str | None) -> BrowserContext:
    return await play.chromium.launch_persistent_context(
        str(USER_DATA), headless=False, channel=channel, viewport=None,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            f"--remote-debugging-port={CDP_PORT}",
        ],
    )


def _locked(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "already in use" in text or "existing browser session" in text or "singletonlock" in text


def _close_orphans() -> None:
    """Shut any browser still holding this project's ChatGPT profile.

    Matched on the profile path, so only windows this project started are
    touched - an everyday Chrome session is never disturbed. A blocking
    subprocess call, accepted here since this only runs on the rare
    profile-locked recovery path, not on every request.
    """
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or "
        "Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*%s*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        % str(USER_DATA).replace("'", "''")
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
            os.remove(USER_DATA / name)
        except OSError:
            pass


def _why(failures: list[Exception]) -> str:
    if any(_locked(e) for e in failures):
        return (
            "A ChatGPT browser window from an earlier run is still holding "
            "the profile, and it could not be closed automatically. Close "
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


# ── Finding elements, filling the composer, reading the reply ───────────


async def _find(page: Page, selectors: list[str], timeout: int = 8000) -> Locator | None:
    """First selector that's actually on the page.

    ChatGPT renames things, so each selector gets a short look before the
    next is tried, and only the last round is given the full wait -
    otherwise a name that no longer exists burns the whole budget before
    the one that works is even reached.
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


async def _visible(page: Page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            if await page.locator(selector).first.is_visible(timeout=400):
                return True
        except Exception:  # noqa: BLE001 - try the next selector
            continue
    return False


async def _fill(page: Page, prompt: str) -> None:
    """Get the whole prompt into the message box, and prove that it's there.

    A resume prompt (profile prompt + full JD + schema instructions) can
    run to tens of thousands of characters. Pasting is much the fastest
    way in, but a long paste can silently be turned into an attached file
    instead of composer text - so what landed is measured, and typing is
    the fallback.
    """
    wanted = len(prompt.strip())

    async def landed() -> int:
        return len((await _composer_text(page)).strip())

    try:
        pyperclip.copy(prompt)
        await page.keyboard.press("Control+V")
        for _ in range(20):  # a big paste takes a moment to render
            await asyncio.sleep(0.3)
            if await landed() >= wanted * 0.9:
                break
    except Exception:  # noqa: BLE001 - clipboard unavailable; typing below covers it
        pass

    if await landed() >= wanted * 0.9:
        return

    # Type it, in pieces so the editor keeps up.
    await _clear(page)
    step = 2000
    for at in range(0, len(prompt), step):
        await page.keyboard.insert_text(prompt[at:at + step])
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.8)

    got = await landed()
    if got >= wanted * 0.9:
        return

    raise ChatError(
        f"Only {got:,} of the {wanted:,} characters reached the ChatGPT box, "
        "so the job description would have been cut short. Nothing was "
        "sent. This usually means ChatGPT turned the paste into an "
        "attachment - try again, or shorten the prompt."
    )


async def _clear(page: Page) -> None:
    try:
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
    except Exception:  # noqa: BLE001 - composer may already be empty
        pass


async def _composer_text(page: Page) -> str:
    for selector in COMPOSER:
        try:
            return (await page.locator(selector).first.inner_text(timeout=1000) or "").strip()
        except Exception:  # noqa: BLE001 - try the next selector
            continue
    return ""


def _same(a: str, b: str) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


async def _answer_text(page: Page) -> str:
    try:
        return (await page.evaluate(_READ_ANSWER) or "").strip()
    except Exception:  # noqa: BLE001 - page not ready yet; caller polls again
        return ""


async def _await_reply(page: Page) -> str:
    """Wait for the answer to finish, then read it.

    Finished means the Stop button has gone *and* the text hasn't grown
    for a few seconds - streaming pauses mid-answer, so checking the Stop
    button alone would cut a reply in half.
    """
    start = time.time()
    deadline = start + REPLY_WAIT
    started = False
    last_text, steady_since = "", None

    while time.time() < deadline:
        streaming = await _visible(page, STOP)
        if streaming:
            started = True

        text = await _answer_text(page)

        if text != last_text:
            last_text, steady_since = text, time.time()
        elif text and not streaming and steady_since:
            if started and time.time() - steady_since >= SETTLE:
                return text
            # Some builds never show a Stop button; settle for longer then.
            if not started and time.time() - steady_since >= SETTLE * 4:
                return text

        # Nothing readable after a fair wait means the reply can't be read
        # rather than that it's slow - say so instead of sitting here until
        # the full timeout.
        if not last_text and not streaming and (time.time() - start) > SILENT_WAIT:
            raise ChatError(
                f"No new reply could be read from the ChatGPT page after "
                f"{SILENT_WAIT} seconds. The message was sent - look at the "
                "browser window. If the answer is there, ChatGPT has "
                "changed its page and this project needs updating to match."
            )
        await asyncio.sleep(0.7)

    if last_text:
        return last_text
    raise ChatError(f"ChatGPT sent no reply within {REPLY_WAIT} seconds.")
