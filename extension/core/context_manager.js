/**
 * Context Manager handling activation state, settings, and provider resolution.
 */

class ContextManager {
  constructor() {
    this.isEnabled = true;
  }

  async loadActivationState() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["memory_layer_enabled"], (result) => {
        if (result.memory_layer_enabled === undefined) {
          this.isEnabled = true;
          chrome.storage.local.set({ memory_layer_enabled: true });
        } else {
          this.isEnabled = !!result.memory_layer_enabled;
        }
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
