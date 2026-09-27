/**
 * Relays messages between the liebao-bid-bot web app (an ordinary page, no
 * special privileges) and this extension's background service worker (which
 * has the chrome.cookies/chrome.tabs access the page itself can't get).
 * Runs only on the app's own origin (see manifest.json's content_scripts
 * match), so no other site's page can talk to the extension this way.
 */

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const msg = event.data;
  if (!msg || msg.source !== "liebao-bid-bot" || msg.direction !== "to-extension") return;

  chrome.runtime.sendMessage({ type: msg.type }, (response) => {
    window.postMessage(
      {
        source: "liebao-bid-bot",
        direction: "from-extension",
        requestId: msg.requestId,
        response,
      },
      "*",
    );
  });
});

// Lets the page detect the extension is actually installed, rather than
// silently waiting forever for a response that will never come.
window.postMessage(
  { source: "liebao-bid-bot", direction: "from-extension", type: "liebao:extensionReady" },
  "*",
);
