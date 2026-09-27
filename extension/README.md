# liebao-bid-bot companion extension

Lets the web app use your **real, already-open Chrome** for sources that
only give full results to a logged-in session (currently: Jobright) -
instead of a separate browser profile you'd have to log into a second time.

No build step; it's loaded straight into Chrome as an unpacked extension.

## Install

1. Go to `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked**, and select this `extension/` folder.
4. It should appear as "liebao-bid-bot companion". No icon is set yet, so
   Chrome shows a generic placeholder - that's expected.

That's it - no login of its own, no popup UI. It just sits in the
background until the web app (running on `localhost:5173` / `127.0.0.1:5173`)
asks it something.

## What it does

- Reads your browser's actual `jobright.ai` cookies (`chrome.cookies`, which
  only an extension can do - the web app itself can't read another site's
  cookies) and relays them to the local backend, which uses them to make
  authenticated requests to Jobright's real API.
- Opens a new tab to Jobright's login page when the web app asks it to
  (e.g. when Run Fetch finds no valid session).

See `docs/ARCHITECTURE.md` for the full message-passing design
(content-script.js relays between the page and background.js).

## After changing the code

Go to `chrome://extensions` and click the reload icon on this extension's
card - Chrome doesn't pick up file changes on its own.
