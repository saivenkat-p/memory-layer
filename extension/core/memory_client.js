/**
 * Core HTTP API Client communicating strictly with the localhost Memory Layer backend.
 *
 * Hardened for V6.7:
 * 1. AbortController / 5000ms fetch timeout protection on all requests.
 * 2. Standardized error envelope handling for offline / timeout scenarios.
 * 3. Strict local API restriction (http://127.0.0.1:8000/api/v1).
 */

class MemoryLayerClient {
  constructor(baseUrl = "http://127.0.0.1:8000/api/v1") {
    this.baseUrl = baseUrl;
    this.DEFAULT_TIMEOUT_MS = 5000;
  }

  async _fetchWithTimeout(url, options = {}, timeoutMs = this.DEFAULT_TIMEOUT_MS) {
    // 1. Attempt direct fetch
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timer);
      return resp;
    } catch (directErr) {
      clearTimeout(timer);

      // 2. Fallback: Proxy via extension service worker (bypasses Chrome page-level Private Network Access restrictions)
      if (typeof chrome !== "undefined" && chrome.runtime && typeof chrome.runtime.sendMessage === "function") {
        try {
          const bgResp = await new Promise((resolve) => {
            const bgTimer = setTimeout(() => resolve({ ok: false, offline: true, error: "Background proxy timeout" }), timeoutMs);
            chrome.runtime.sendMessage({ type: "API_REQUEST", url, options }, (response) => {
              clearTimeout(bgTimer);
              if (chrome.runtime && chrome.runtime.lastError) {
                resolve({ ok: false, offline: true, error: chrome.runtime.lastError.message });
              } else {
                resolve(response || { ok: false, offline: true });
              }
            });
          });

          if (bgResp && bgResp.data !== undefined) {
            return {
              ok: bgResp.ok,
              status: bgResp.status || (bgResp.ok ? 200 : 500),
              json: async () => bgResp.data
            };
          }
        } catch (bgErr) {
          // Fall through
        }
      }

      if (directErr.name === "AbortError") {
        throw new Error(`Request timed out after ${timeoutMs}ms`);
      }
      throw directErr;
    }
  }

  async checkHealth() {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/health`, { method: "GET" });
      if (!resp.ok) return { status: "error", message: `HTTP ${resp.status}`, offline: true };
      return await resp.json();
    } catch (e) {
      return { status: "offline", error: e.message, offline: true };
    }
  }

  async searchGlobal(query, limit = 20) {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Global search offline/failed:", e.message);
      return { error: true, message: e.message, results: [], offline: true };
    }
  }

  async searchInConversation(conversationId, query, limit = 20) {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/search/conversation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId, query, limit })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] In-conversation search offline/failed:", e.message);
      return { error: true, message: e.message, results: [], offline: true };
    }
  }

  async composeContext(query, maxCandidates = 10) {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/context/compose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, max_candidates: maxCandidates })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Context composition offline/failed:", e.message);
      return { error: true, message: e.message, offline: true };
    }
  }

  async syncConversation(syncPayload) {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/conversations/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(syncPayload)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Conversation sync offline/failed:", e.message);
      return { error: true, message: e.message, offline: true };
    }
  }

  async createChildConversation(parentConversationId, title, sourceMessageIds = [], provider = "ChatGPT") {
    try {
      const resp = await this._fetchWithTimeout(`${this.baseUrl}/conversations/child`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent_conversation_id: parentConversationId,
          title: title,
          source_message_ids: sourceMessageIds,
          provider: provider
        })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Create child conversation offline/failed:", e.message);
      return { error: true, message: e.message, offline: true };
    }
  }

  // =========================================================================
  // STRUCTURED MEMORIES API (Milestone V6.5-E4 / Memory UX)
  // =========================================================================

  async listMemories(options = {}) {
    try {
      const params = new URLSearchParams();
      if (options.type) params.set("type", options.type);
      if (options.conversation_id) params.set("conversation_id", options.conversation_id);
      if (options.status) params.set("status", options.status);
      if (options.limit) params.set("limit", options.limit);
      if (options.offset) params.set("offset", options.offset);
      if (options.hydrate !== undefined) params.set("hydrate", options.hydrate ? "true" : "false");

      const qs = params.toString();
      const url = `${this.baseUrl}/memories${qs ? `?${qs}` : ""}`;
      const resp = await this._fetchWithTimeout(url, { method: "GET" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] List memories offline/failed:", e.message);
      return { error: true, message: e.message, memories: [], total: 0, offline: true };
    }
  }

  async searchMemories(query, options = {}) {
    try {
      const payload = {
        query: query || "",
        type: options.type || undefined,
        conversation_id: options.conversation_id || undefined,
        status: options.status || "active",
        limit: options.limit || 20,
        threshold: options.threshold !== undefined ? options.threshold : 0.35,
        hydrate: options.hydrate !== undefined ? options.hydrate : true
      };

      const resp = await this._fetchWithTimeout(`${this.baseUrl}/memories/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Search memories offline/failed:", e.message);
      return { error: true, message: e.message, results: [], total: 0, offline: true };
    }
  }

  async getMemory(memoryId, hydrate = true) {
    try {
      const url = `${this.baseUrl}/memories/${encodeURIComponent(memoryId)}?hydrate=${hydrate ? "true" : "false"}`;
      const resp = await this._fetchWithTimeout(url, { method: "GET" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Get memory offline/failed:", e.message);
      return { error: true, message: e.message, not_found: true, offline: true };
    }
  }

  async deleteMemory(memoryId) {
    try {
      const url = `${this.baseUrl}/memories/${encodeURIComponent(memoryId)}`;
      const resp = await this._fetchWithTimeout(url, { method: "DELETE" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn("[MemoryLayerClient] Delete memory offline/failed:", e.message);
      return { error: true, message: e.message, offline: true };
    }
  }
}

// Global instance attached to window for content script usage
window.MemoryLayerClientInstance = new MemoryLayerClient();
