/**
 * Core HTTP API Client communicating strictly with the localhost Memory Layer backend.
 */

class MemoryLayerClient {
  constructor(baseUrl = "http://127.0.0.1:8000/api/v1") {
    this.baseUrl = baseUrl;
  }

  async checkHealth() {
    try {
      const resp = await fetch(`${this.baseUrl}/health`, { method: "GET" });
      if (!resp.ok) return { status: "error", message: `HTTP ${resp.status}` };
      return await resp.json();
    } catch (e) {
      return { status: "offline", error: e.message };
    }
  }

  async searchGlobal(query, limit = 20) {
    try {
      const resp = await fetch(`${this.baseUrl}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.error("[MemoryLayerClient] Global search failed:", e);
      return { error: true, message: e.message, results: [] };
    }
  }

  async searchInConversation(conversationId, query, limit = 20) {
    try {
      const resp = await fetch(`${this.baseUrl}/search/conversation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId, query, limit })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.error("[MemoryLayerClient] In-conversation search failed:", e);
      return { error: true, message: e.message, results: [] };
    }
  }

  async composeContext(query, maxCandidates = 10) {
    try {
      const resp = await fetch(`${this.baseUrl}/context/compose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, max_candidates: maxCandidates })
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.error("[MemoryLayerClient] Context composition failed:", e);
      return { error: true, message: e.message };
    }
  }

  async syncConversation(syncPayload) {
    try {
      const resp = await fetch(`${this.baseUrl}/conversations/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(syncPayload)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.error("[MemoryLayerClient] Conversation sync failed:", e);
      return { error: true, message: e.message };
    }
  }
}

// Global instance attached to window for content script usage
window.MemoryLayerClientInstance = new MemoryLayerClient();

