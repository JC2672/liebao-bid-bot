/**
 * liebao-bid-bot companion extension - background service worker.
 *
 * Purpose: some sources (starting with Jobright) only give full results to a
 * logged-in session, and the whole point of this extension is to use the
 * user's REAL, already-open Chrome for that - not a separate automation
 * profile the user has to log into a second time. This worker reads the
 * relevant cookies from the user's actual browser (chrome.cookies, which
 * only an extension can do) and relays them to the local backend so its
 * plain `requests` calls can carry the same session.
 */

const BACKEND_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"];

async function postToBackend(path, body) {
  let lastError;
  for (const origin of BACKEND_ORIGINS) {
    try {
      const resp = await fetch(`${origin}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return await resp.json();
    } catch (err) {
      lastError = err; // try the next origin (VPNs can break "localhost" - see start.bat)
    }
  }
  throw lastError;
}

async function checkAndSyncJobright() {
  const cookies = await chrome.cookies.getAll({ domain: "jobright.ai" });
  if (cookies.length === 0) {
    return { loggedIn: false };
  }
  const payload = cookies.map((c) => ({ name: c.name, value: c.value, domain: c.domain }));
  try {
    const data = await postToBackend("/sources/jobright/cookies", { cookies: payload });
    return { loggedIn: !!data.logged_in };
  } catch (err) {
    return { loggedIn: false, error: String(err) };
  }
}

function openJobrightLogin() {
  chrome.tabs.create({ url: "https://jobright.ai/jobs/search" });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "liebao:checkJobrightSession") {
    checkAndSyncJobright().then(sendResponse);
    return true; // keep the message channel open for the async response
  }
  if (message?.type === "liebao:openJobrightLogin") {
    openJobrightLogin();
    sendResponse({ ok: true });
    return true;
  }
  return false;
});
