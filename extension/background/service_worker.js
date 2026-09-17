/**
 * Background Service Worker for Personal AI Memory Layer Extension (Manifest V3).
 */

console.log("[Memory Layer Extension] Background Service Worker initialized.");

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Memory Layer Extension] Extension installed. Initializing storage defaults (enabled by default)...");
  chrome.storage.local.get(["memory_layer_enabled"], (result) => {
    if (result.memory_layer_enabled === undefined) {
      chrome.storage.local.set({ memory_layer_enabled: true });
    }
  });
});

// Proxy HTTP requests to localhost backend (bypasses page-level Private Network Access / CSP restrictions)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request && request.type === "API_REQUEST") {
    const { url, options } = request;
    fetch(url, options)
      .then(async (resp) => {
        const data = await resp.json().catch(() => ({}));
        sendResponse({ ok: resp.ok, status: resp.status, data });
      })
      .catch((err) => {
        console.warn("[ServiceWorker] API proxy fetch offline/failed:", err.message);
        sendResponse({ ok: false, error: err.message, offline: true });
      });
    return true; // Keep message channel open for async response
  }
});
