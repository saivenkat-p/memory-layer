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
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timer);
      return resp;
    } catch (e) {
      clearTimeout(timer);
      if (e.name === "AbortError") {
        throw new Error(`Request timed out after ${timeoutMs}ms`);
      }
      throw e;
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
      console.error("[MemoryLayerClient] Global search failed:", e);
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
      console.error("[MemoryLayerClient] In-conversation search failed:", e);
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
      console.error("[MemoryLayerClient] Context composition failed:", e);
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
      console.error("[MemoryLayerClient] Conversation sync failed:", e);
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
      console.error("[MemoryLayerClient] List memories failed:", e);
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
      console.error("[MemoryLayerClient] Search memories failed:", e);
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
      console.error("[MemoryLayerClient] Get memory failed:", e);
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
      console.error("[MemoryLayerClient] Delete memory failed:", e);
      return { error: true, message: e.message, offline: true };
    }
  }
}

// Global instance attached to window for content script usage
window.MemoryLayerClientInstance = new MemoryLayerClient();
