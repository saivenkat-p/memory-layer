document.addEventListener("DOMContentLoaded", async () => {
  const toggle = document.getElementById("activationToggle");
  const statusText = document.getElementById("activationStatusText");
  const statusBadge = document.getElementById("statusBadge");
  const backendDetail = document.getElementById("backendDetail");

  const client = window.MemoryLayerClientInstance || new MemoryLayerClient();
  const manager = window.ContextManagerInstance || new ContextManager();

  // Load initial activation state
  const isEnabled = await manager.loadActivationState();
  toggle.checked = isEnabled;
  updateStatusText(isEnabled);

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

  // Handle toggle change
  toggle.addEventListener("change", async (e) => {
    const newState = e.target.checked;
    await manager.setActivationState(newState);
    updateStatusText(newState);

    // Notify active tabs
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0] && tabs[0].id) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "MEMORY_LAYER_TOGGLED", enabled: newState });
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
});
