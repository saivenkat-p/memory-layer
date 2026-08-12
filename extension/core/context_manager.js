/**
 * Context Manager handling activation state, settings, and provider resolution.
 */

class ContextManager {
  constructor() {
    this.isEnabled = true;
    this.isAutoSyncEnabled = false; // Default OFF as per Directive
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

  async loadAutoSyncState() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["memory_layer_auto_sync"], (result) => {
        if (result.memory_layer_auto_sync === undefined) {
          this.isAutoSyncEnabled = false; // Default OFF
          chrome.storage.local.set({ memory_layer_auto_sync: false });
        } else {
          this.isAutoSyncEnabled = !!result.memory_layer_auto_sync;
        }
        resolve(this.isAutoSyncEnabled);
      });
    });
  }

  async setAutoSyncState(enabled) {
    this.isAutoSyncEnabled = !!enabled;
    return new Promise((resolve) => {
      chrome.storage.local.set({ memory_layer_auto_sync: this.isAutoSyncEnabled }, () => {
        resolve(this.isAutoSyncEnabled);
      });
    });
  }
}

window.ContextManagerInstance = new ContextManager();

