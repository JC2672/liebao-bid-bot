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
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import pyperclip
from playwright.async_api import BrowserContext, Locator, Page, Playwright, async_playwright

from . import browser_launch

# Called with a short human-readable progress note (currently just the
# login wait) - see ask()'s docstring.
StatusCallback = Callable[[str], None] | None

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

# The logged-out landing page's own "Log in" button - a direct signal,
# checked *first*, rather than inferring "not logged in" from the composer
# being absent. That inference was the original approach and turned out
# unreliable in testing: COMPOSER's last two selectors ("form textarea",
# bare "textarea") are generic enough to occasionally match something
# unrelated on the landing page, making the code think it had found the
# real composer when it hadn't - confirmed live as a real failure mode,
# not a hypothetical one.
LOGIN_BUTTON = ["[data-testid='login-button']", "a[href*='/auth/login']", "button:has-text('Log in')"]

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


async def ask(parts: list[str], new_chat: bool = True, on_status: StatusCallback = None) -> str:
    """Send a prompt as one or more separate chat turns, return the reply
    text from the LAST turn only.

    `parts` (the profile prompt, then the job description, typically) are
    sent as separate messages - send the first, wait for ChatGPT to fully
    finish responding to it, send the next, and so on - rather than pasted
    together into one giant message. Confirmed live as a real failure mode:
    a single huge paste is what triggers ChatGPT's own heuristic to convert
    a long paste into a .txt attachment instead of composer text, and that
    conversion isn't reliably atomic under slow network/render conditions -
    it can leave an attachment *and* leftover raw text, or land late and
    end up duplicated underneath a fallback that assumed the paste had
    failed. Splitting into smaller, separately-sent messages keeps any
    single paste well clear of whatever triggers that, and there's no
    "reply" to get wrong for the earlier turns - only the final turn's
    answer is read and returned.

    Runs on the dedicated Playwright thread (see module docstring for why),
    bridged back into the caller's own event loop via
    `run_coroutine_threadsafe`. Only one call runs at a time on that thread
    (there's only one browser, one conversation) - concurrent callers
    simply wait their turn. `new_chat=False` would continue the chat
    already open (not used by this project yet, but kept since a follow-up
    like job_finder's score/revise loop is a plausible later addition).

    `on_status`, if given, is called (from the dedicated thread, not the
    caller's) with short human-readable progress notes - currently just
    the login wait, so a row stuck on `generating` for that reason shows
    *why* instead of sitting silent for up to LOGIN_WAIT seconds before
    finally erroring out. Never raises on its own account; a failure in
    the callback shouldn't take down the actual generation.
    """
    loop = _ensure_thread()
    future = asyncio.run_coroutine_threadsafe(_ask_on_thread(parts, new_chat, on_status), loop)
    return await asyncio.wrap_future(future)


async def _ask_on_thread(parts: list[str], new_chat: bool, on_status: StatusCallback) -> str:
    assert _lock is not None
    async with _lock:
        return await _converse(parts, new_chat, on_status)


def _report(on_status: StatusCallback, message: str) -> None:
    if on_status is None:
        return
    try:
        on_status(message)
    except Exception:  # noqa: BLE001 - a broken status callback shouldn't fail the generation itself
        pass


async def _converse(parts: list[str], new_chat: bool, on_status: StatusCallback) -> str:
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

        # Checked first, directly - not inferred from the composer being
        # absent (see LOGIN_BUTTON's own comment for why that was unreliable).
        # Nothing is typed or pasted into the composer until this resolves
        # either way - the whole point is that a login prompt never gets a
        # job description silently thrown at it.
        if await browser_launch.visible(page, LOGIN_BUTTON):
            box = await _wait_for_login(page, on_status)
        else:
            box = await browser_launch.find(page, COMPOSER, timeout=15000)
            if box is None:
                box = await _wait_for_login(page, on_status)

        multi_turn = len(parts) > 1
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            if i > 0:
                # Sent already; ChatGPT clears/refocuses its own composer on
                # send, so this is just re-finding the same box, fresh.
                box = await browser_launch.find(page, COMPOSER, timeout=15000)
                if box is None:
                    raise ChatError("ChatGPT's message box disappeared mid-conversation - look at the browser window.")

            await box.click()
            await _fill_one(page, part)

            send = await browser_launch.find(page, SEND, timeout=4000)
            if send is not None:
                await send.click()
            else:
                await page.keyboard.press("Enter")

            if is_last:
                return await _await_reply(page)

            if multi_turn:
                _report(on_status, "Sent the prompt - waiting for ChatGPT before sending the job description...")
            await _wait_for_turn_complete(page)

        raise ChatError("Nothing to send.")  # unreachable: parts always has at least one item
    except ChatError:
        raise
    except Exception as exc:
        # A broken page isn't worth keeping; the next call reopens it.
        _context = _page = None
        raise ChatError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc


async def _wait_for_login(page: Page, on_status: StatusCallback) -> Locator:
    _report(on_status, "Waiting for you to sign in to ChatGPT - check the browser window that opened.")
    deadline = time.time() + LOGIN_WAIT
    while time.time() < deadline:
        if not await browser_launch.visible(page, LOGIN_BUTTON):
            box = await browser_launch.find(page, COMPOSER, timeout=3000)
            if box is not None:
                _report(on_status, "Signed in - continuing.")
                return box
        else:
            await asyncio.sleep(1)
    raise ChatError(
        "No ChatGPT message box appeared. Sign in to chatgpt.com in the "
        "window that opened, then click Generate again - the sign-in is "
        "remembered after that."
    )


# ── Opening the browser ────────────────────────────────────────────────


async def _open() -> tuple[BrowserContext, Page]:
    """A Chrome window signed into ChatGPT, reusing the saved profile."""
    global _playwright
    if _playwright is None:
        _playwright = await async_playwright().start()
    try:
        return await browser_launch.open_persistent_context(_playwright, USER_DATA, CDP_PORT)
    except browser_launch.LaunchError as exc:
        raise ChatError(str(exc)) from exc


# ── Finding elements, filling the composer, reading the reply ───────────


async def _wait_for_turn_complete(page: Page) -> None:
    """Wait for ChatGPT to fully finish responding to the message just
    sent - the Stop button gone, and staying gone for a settle period -
    without reading or caring about that reply's text. Used between turns
    of a multi-part prompt sent as separate messages (the profile prompt,
    then the job description) rather than one combined message; only the
    LAST turn's reply is the one this project actually wants."""
    deadline = time.time() + REPLY_WAIT
    settled_since = None
    while time.time() < deadline:
        if await browser_launch.visible(page, STOP):
            settled_since = None
        else:
            if settled_since is None:
                settled_since = time.time()
            elif time.time() - settled_since >= SETTLE:
                return
        await asyncio.sleep(0.5)
    raise ChatError(
        f"ChatGPT never finished responding to the prompt message within "
        f"{REPLY_WAIT} seconds, so the job description was never sent. Look "
        "at the browser window."
    )


async def _fill_one(page: Page, text: str) -> None:
    """Get one message's worth of text into the composer, and prove it's
    there.

    A message here can run to tens of thousands of characters. Pasting is
    much the fastest way in, but a long paste can silently be turned into
    an attached file instead of composer text - confirmed live,
    inconsistently, especially under slow network/render conditions, where
    the conversion can leave an attachment *and* leftover raw composer
    text, or land late and end up duplicated underneath a typed fallback
    that assumed the paste had failed outright. Sending the prompt as
    smaller separate messages (see `ask`'s docstring) rather than one giant
    one already reduces how often any single paste is large enough to trip
    that in the first place; what landed is still measured here regardless,
    and typing is the fallback if it didn't.
    """
    wanted = len(text.strip())

    async def landed() -> int:
        return len((await _composer_text(page)).strip())

    # Always start from an empty box - matters most for the very first
    # message (a stale render, a previous attempt's leftover text); later
    # turns already start from an empty composer since ChatGPT clears its
    # own on send, so this is a harmless no-op then.
    await _clear(page)

    try:
        pyperclip.copy(text)
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
    for at in range(0, len(text), step):
        await page.keyboard.insert_text(text[at:at + step])
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.8)

    got = await landed()
    if got >= wanted * 0.9:
        return

    raise ChatError(
        f"Only {got:,} of the {wanted:,} characters reached the ChatGPT box, "
        "so the message would have been cut short. Nothing was sent. This "
        "usually means ChatGPT turned the paste into an attachment - try "
        "again, or shorten the prompt."
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
        streaming = await browser_launch.visible(page, STOP)
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
