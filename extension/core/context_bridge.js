/**
 * Cross-AI Context Bridge Engine for Personal AI Memory Layer.
 *
 * Implements the cross-AI context packaging and destination workflow:
 * 1. Multi-source context selection tracking (messages & structured memories).
 * 2. Deterministic, provenance-preserving Markdown context packaging.
 * 3. Destination routing (Current Chat, New Chat, Clipboard Copy).
 * 4. Pending context injection across new conversation page navigation.
 */

class ContextBridge {
  constructor() {
    this.selectedItems = new Map(); // id -> itemData
    this.STORAGE_KEY = "ml_pending_context";
  }

  addItem(item) {
    if (!item || !item.id) return;
    this.selectedItems.set(item.id, {
      id: item.id,
      conversationId: item.conversationId || item.conversation_id || "unknown",
      conversationTitle: item.conversationTitle || item.conversation_title || item.conversation_id || "Conversation",
      provider: item.provider || item.source || "AI",
      role: item.role || item.matched_role || "assistant",
      turnIndex: item.turnIndex !== undefined ? item.turnIndex : item.index,
      content: item.content || item.matched_content || item.snippet || "",
      memoryType: item.memoryType || item.memory_type || null,
      timestamp: item.timestamp || new Date().toISOString()
    });
  }

  removeItem(id) {
    this.selectedItems.delete(id);
  }

  clear() {
    this.selectedItems.clear();
  }

  hasItem(id) {
    return this.selectedItems.has(id);
  }

  getItems() {
    return Array.from(this.selectedItems.values());
  }

  getCount() {
    return this.selectedItems.size;
  }

  /**
   * Packages selected items into a clean, structured multi-source Markdown format.
   */
  formatContextPackage(items = null, options = {}) {
    const list = items || this.getItems();
    if (!list.length) return "";

    // Group items by conversationId preserving source metadata
    const groups = new Map(); // convId -> { title, provider, items: [] }

    list.forEach((it) => {
      const convId = it.conversationId || "unknown";
      if (!groups.has(convId)) {
        groups.set(convId, {
          title: it.conversationTitle || convId,
          provider: it.provider || "AI",
          items: []
        });
      }
      groups.get(convId).items.push(it);
    });

    let out = "[Personal AI Memory Layer — Cross-AI Context Reference]:\n";

    let sourceIdx = 1;
    groups.forEach((grp, convId) => {
      out += `\n• SOURCE ${sourceIdx}: ${grp.provider} — "${grp.title}" (ID: ${convId})\n`;

      // Sort items within group by turnIndex if available
      grp.items.sort((a, b) => {
        const idxA = a.turnIndex !== undefined ? a.turnIndex : 0;
        const idxB = b.turnIndex !== undefined ? b.turnIndex : 0;
        return idxA - idxB;
      });

      grp.items.forEach((item) => {
        const roleTag = item.role ? `[${item.role}]` : "";
        const turnTag = item.turnIndex !== undefined ? `Turn ${item.turnIndex}` : "";
        const memTypeTag = item.memoryType ? `⚡ ${item.memoryType.toUpperCase()}: ` : "";
        const label = [turnTag, roleTag].filter(Boolean).join(" ");
        const prefix = label ? `  - ${label}: ` : "  - ";

        out += `${prefix}${memTypeTag}"${item.content.trim()}"\n`;
      });

      sourceIdx += 1;
    });

    out += "\n";
    return out;
  }

  /**
   * Applies formatted context to the current chat composer (INSERT ONLY).
   */
  applyToCurrentChat(adapter, packagedText = null) {
    if (!adapter) return false;
    const text = packagedText || this.formatContextPackage();
    if (!text) return false;
    return adapter.insertText(text);
  }

  /**
   * Prepares pending context in sessionStorage and initiates New Chat navigation.
   */
  applyToNewChat(adapter, packagedText = null) {
    if (!adapter) return false;
    const text = packagedText || this.formatContextPackage();
    if (!text) return false;

    try {
      sessionStorage.setItem(this.STORAGE_KEY, text);
    } catch (e) {
      console.warn("[ContextBridge] Could not save pending context to sessionStorage:", e);
    }

    return adapter.startNewChat();
  }

  /**
   * Checks for and consumes pending context upon page load.
   */
  checkAndConsumePendingContext(adapter) {
    if (!adapter) return false;
    try {
      const pending = sessionStorage.getItem(this.STORAGE_KEY);
      if (pending) {
        sessionStorage.removeItem(this.STORAGE_KEY);
        // Delay slightly for composer DOM hydration
        setTimeout(() => {
          adapter.insertText(pending);
        }, 1000);
        return true;
      }
    } catch (e) {
      console.warn("[ContextBridge] Error consuming pending context:", e);
    }
    return false;
  }

  /**
   * Copies packaged text to system clipboard.
   */
  async copyToClipboard(packagedText = null) {
    const text = packagedText || this.formatContextPackage();
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      console.error("[ContextBridge] Clipboard copy failed:", e);
      return false;
    }
  }
}

// Global instance attached to window for extension content scripts
window.ContextBridgeInstance = new ContextBridge();
