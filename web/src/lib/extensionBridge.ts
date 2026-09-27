/**
 * Talks to the companion Chrome extension (extension/), which runs in the
 * user's real, already-open Chrome - not a separate browser profile. A
 * content script it injects into this page relays messages to its
 * background service worker, which has the chrome.cookies/chrome.tabs
 * access this ordinary page can't get itself. See extension/content-script.js
 * for the other half of this handshake.
 */

interface ExtensionMessage {
  source: "liebao-bid-bot";
  direction: "to-extension" | "from-extension";
  type?: string;
  requestId?: number;
  response?: unknown;
}

let requestCounter = 0;
const pending = new Map<number, (response: unknown) => void>();
let extensionDetected = false;

if (typeof window !== "undefined") {
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const msg = event.data as ExtensionMessage;
    if (!msg || msg.source !== "liebao-bid-bot" || msg.direction !== "from-extension") return;

    if (msg.type === "liebao:extensionReady") {
      extensionDetected = true;
      return;
    }
    if (msg.requestId != null && pending.has(msg.requestId)) {
      pending.get(msg.requestId)!(msg.response);
      pending.delete(msg.requestId);
    }
  });
}

function sendToExtension<T>(type: string, timeoutMs = 3000): Promise<T | null> {
  return new Promise((resolve) => {
    const requestId = ++requestCounter;
    const timer = setTimeout(() => {
      pending.delete(requestId);
      resolve(null);
    }, timeoutMs);
    pending.set(requestId, (response) => {
      clearTimeout(timer);
      resolve(response as T);
    });
    window.postMessage({ source: "liebao-bid-bot", direction: "to-extension", type, requestId }, "*");
  });
}

export async function isExtensionInstalled(): Promise<boolean> {
  if (extensionDetected) return true;
  // The content script's "ready" announcement may not have arrived yet on a
  // fresh page load - give it a brief moment before concluding it's missing.
  await new Promise((r) => setTimeout(r, 300));
  return extensionDetected;
}

export async function checkJobrightSession(): Promise<boolean> {
  const result = await sendToExtension<{ loggedIn: boolean }>("liebao:checkJobrightSession");
  return result?.loggedIn ?? false;
}

export async function openJobrightLoginTab(): Promise<void> {
  await sendToExtension("liebao:openJobrightLogin");
}
