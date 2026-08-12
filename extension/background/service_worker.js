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
