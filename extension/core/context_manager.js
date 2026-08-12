/**
 * Context Manager handling activation state, settings, and provider resolution.
 */

class ContextManager {
  constructor() {
    this.isEnabled = false;
  }

  async loadActivationState() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["memory_layer_enabled"], (result) => {
        this.isEnabled = !!result.memory_layer_enabled;
        resolve(this.isEnabled);
      });
    });
  }

  async setActivationState(enabled) {
    this.isEnabled = !!enabled;
    return new Promise((resolve) => {
      chrome.storage.local.set({ memory_layer_enabled: this.isEnabled }, () => {
        resolve(this.isEnabled);
      });
    });
  }
}

window.ContextManagerInstance = new ContextManager();
