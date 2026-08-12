document.addEventListener("DOMContentLoaded", async () => {
  const toggle = document.getElementById("activationToggle");
  const autoSyncToggle = document.getElementById("autoSyncToggle");
  const statusText = document.getElementById("activationStatusText");
  const autoSyncStatusText = document.getElementById("autoSyncStatusText");
  const statusBadge = document.getElementById("statusBadge");
  const backendDetail = document.getElementById("backendDetail");

  const client = window.MemoryLayerClientInstance || new MemoryLayerClient();
  const manager = window.ContextManagerInstance || new ContextManager();

  // Load initial activation & auto-sync states
  const isEnabled = await manager.loadActivationState();
  toggle.checked = isEnabled;
  updateStatusText(isEnabled);

  const isAutoSyncEnabled = await manager.loadAutoSyncState();
  autoSyncToggle.checked = isAutoSyncEnabled;
  updateAutoSyncStatusText(isAutoSyncEnabled);

  // Check backend API connection
  const health = await client.checkHealth();
  if (health.status === "ok") {
    statusBadge.textContent = "Online";
    statusBadge.className = "badge online";
    backendDetail.textContent = `Connected (v${health.version})`;
  } else {
    statusBadge.textContent = "Offline";
    statusBadge.className = "badge offline";
    backendDetail.textContent = "Backend offline. Launch 'python -m app.api.server'";
  }

  // Handle activation toggle change
  toggle.addEventListener("change", async (e) => {
    const newState = e.target.checked;
    await manager.setActivationState(newState);
    updateStatusText(newState);

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0] && tabs[0].id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "MEMORY_LAYER_TOGGLED", enabled: newState });
      }
    });
  });

  // Handle auto-sync toggle change
  autoSyncToggle.addEventListener("change", async (e) => {
    const newState = e.target.checked;
    await manager.setAutoSyncState(newState);
    updateAutoSyncStatusText(newState);

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0] && tabs[0].id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "MEMORY_LAYER_AUTO_SYNC_TOGGLED", autoSyncEnabled: newState });
      }
    });
  });

  function updateStatusText(enabled) {
    if (enabled) {
      statusText.innerHTML = "Memory Layer is <strong style='color:#10b981;'>Enabled</strong> on supported AI websites.";
    } else {
      statusText.innerHTML = "Memory Layer is <strong style='color:#ef4444;'>Disabled</strong>. No features injected.";
    }
  }

  function updateAutoSyncStatusText(autoSyncEnabled) {
    if (autoSyncEnabled) {
      autoSyncStatusText.innerHTML = "Auto-sync is <strong style='color:#10b981;'>ON</strong>. Rendered web chats will sync locally.";
    } else {
      autoSyncStatusText.innerHTML = "Auto-sync is <strong>OFF</strong> (Default). Conversations are not automatically saved.";
    }
  }
});

