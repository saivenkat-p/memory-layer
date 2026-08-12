/**
 * Opt-In Auto-Sync Engine (Milestone V6.2.x).
 *
 * Responsibilities:
 * 1. Checks if Auto-sync toggle is explicitly ON (`chrome.storage.local`).
 * 2. Reads rendered DOM messages using the current provider adapter.
 * 3. Extracts deterministic conversation ID, title, and normalized message turns.
 * 4. Debounces sync operations to wait until streaming responses stabilize.
 * 5. Prevents duplicate HTTP requests using content fingerprint hashes.
 * 6. Fails gracefully if the local API backend is offline.
 */

class ConversationSyncEngine {
  constructor() {
    this.client = window.MemoryLayerClientInstance || new MemoryLayerClient();
    this.manager = window.ContextManagerInstance || new ContextManager();
    this.currentAdapter = null;
    this.isAutoSyncEnabled = false;
    this.isObserverStarted = false;
    this.debounceTimer = null;
    this.lastSyncedHash = "";
    this.lastObservedPath = "";
  }

  async init(adapter) {
    this.currentAdapter = adapter;
    this.isAutoSyncEnabled = await this.manager.loadAutoSyncState();
    console.log(`[SyncEngine] Initialized for provider ${adapter.getProviderName()} (Auto-sync: ${this.isAutoSyncEnabled})`);

    // Listen for toggle changes from popup
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "MEMORY_LAYER_AUTO_SYNC_TOGGLED") {
        this.isAutoSyncEnabled = !!msg.autoSyncEnabled;
        console.log(`[SyncEngine] Auto-sync setting updated: ${this.isAutoSyncEnabled}`);
        if (this.isAutoSyncEnabled) {
          this.startDOMObserver();
          this.triggerDebouncedSync();
        }
      }
    });

    if (this.isAutoSyncEnabled) {
      this.startDOMObserver();
    }
  }

  startDOMObserver() {
    if (this.isObserverStarted) return;
    this.isObserverStarted = true;
    this.lastObservedPath = window.location.pathname;

    // 1. Initial sync attempt
    this.triggerDebouncedSync();

    // 2. Observer for SPA navigation & DOM changes
    const observer = new MutationObserver(() => {
      if (!this.isAutoSyncEnabled) return;

      // Reset tracking if SPA navigation occurred
      if (window.location.pathname !== this.lastObservedPath) {
        this.lastObservedPath = window.location.pathname;
        this.lastSyncedHash = "";
      }

      this.triggerDebouncedSync();
    });

    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  triggerDebouncedSync() {
    if (!this.isAutoSyncEnabled || !this.currentAdapter) return;

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    // 1500ms Debounce Buffer to allow token streaming to stabilize
    this.debounceTimer = setTimeout(() => {
      this.executeSync();
    }, 1500);
  }

  async executeSync() {
    if (!this.isAutoSyncEnabled || !this.currentAdapter) return;

    // Check if assistant is currently streaming tokens
    if (this.isAssistantStreaming()) {
      console.log("[SyncEngine] Assistant is actively streaming response. Deferring sync...");
      this.triggerDebouncedSync();
      return;
    }

    const messages = this.currentAdapter.readVisibleMessages();
    if (!messages || messages.length === 0) return;

    const provider = this.currentAdapter.getProviderName();
    const title = this.currentAdapter.getCurrentConversationTitle();
    const conversationId = this.deriveConversationId(provider);

    // Compute simple content fingerprint hash
    const rawFingerprint = `${conversationId}:${title}:${messages.length}:${messages.map(m => m.content.slice(0, 30)).join("|")}`;
    if (rawFingerprint === this.lastSyncedHash) {
      return; // Already synced this exact snapshot
    }

    const payload = {
      provider,
      conversation_id: conversationId,
      title: title || `${provider} Conversation`,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
        index: m.index
      }))
    };

    console.log(`[SyncEngine] Syncing conversation '${payload.title}' (${messages.length} msgs) to Memory Layer...`);
    const res = await this.client.syncConversation(payload);

    if (res && res.success) {
      this.lastSyncedHash = rawFingerprint;
      console.log(`[SyncEngine] ✅ Synced successfully: '${res.conversation_id}' (${res.messages_synced} msgs)`);
    } else {
      console.warn("[SyncEngine] Sync response warning:", res);
    }
  }

  isAssistantStreaming() {
    // Check precise streaming indicators across ChatGPT & Gemini
    const streamingEl = document.querySelector(
      '[data-is-streaming="true"], .result-streaming, button[aria-label="Stop generating"], button[aria-label="Stop response"], [data-testid="stop-button"]'
    );
    return !!streamingEl;
  }

  deriveConversationId(provider) {
    const path = window.location.pathname;
    // Extract ChatGPT URL ID if available (e.g. /c/67a2f...)
    const chatgptMatch = path.match(/\/c\/([a-zA-Z0-9-]+)/);
    if (chatgptMatch) {
      return `chatgpt-${chatgptMatch[1]}`;
    }

    // Extract Gemini URL ID if available (e.g. /app/<id>)
    const geminiMatch = path.match(/\/app\/([a-zA-Z0-9-]+)/);
    if (geminiMatch) {
      return `gemini-${geminiMatch[1]}`;
    }

    // Fallback: Title & hostname hash
    const host = window.location.hostname;
    const title = this.currentAdapter ? this.currentAdapter.getCurrentConversationTitle() : "chat";
    const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]/g, "-").slice(0, 40);
    return `${provider.toLowerCase()}-session-${cleanTitle}`;
  }
}

window.ConversationSyncEngineInstance = new ConversationSyncEngine();
