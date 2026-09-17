/**
 * Claude Provider Adapter (Structured Stub — Planned for V6.7).
 *
 * NOTE: As per Directive 3, this adapter is a structured stub until manually verified.
 */

class ClaudeAdapter extends BaseProviderAdapter {
  constructor() {
    super();
    this.name = "Claude";
  }

  isSupported() {
    return false; // Stub until V6.7 manual verification
  }

  matchesPage() {
    return window.location.hostname.includes("claude.ai");
  }

  getCurrentConversationTitle() {
    return "Claude Conversation";
  }

  getCurrentConversationId() {
    const path = window.location.pathname;
    const match = path.match(/\/chat\/([a-f0-9-]+)/i);
    if (match) {
      return match[1];
    }
    return null;
  }

  getComposer() {
    // Basic selector candidate for claude.ai
    return document.querySelector('div[contenteditable="true"], textarea');
  }

  readVisibleMessages() {
    const messageElements = document.querySelectorAll(
      '[data-test-render-count], .font-user-message, .font-claude-message, div[class*="ChatMessage"], div[class*="human"], div[class*="assistant"]'
    );
    const messages = [];
    messageElements.forEach((el, index) => {
      let role = "assistant";
      const cls = el.className || "";
      if (cls.includes("user") || cls.includes("human")) {
        role = "user";
      }
      const textContent = el.textContent ? el.textContent.trim() : "";
      if (textContent) {
        messages.push({
          index,
          role,
          content: textContent,
          isDomVisible: true,
          element: el
        });
      }
    });
    return messages;
  }

  findMessageElement(messageRef) {
    if (!messageRef) return null;
    if (messageRef instanceof HTMLElement) return messageRef;
    if (messageRef && messageRef.element instanceof HTMLElement) return messageRef.element;

    const visible = this.readVisibleMessages();

    // 1. By turn index
    if (typeof messageRef === "number") {
      const byIdx = visible.find((m) => m.index === messageRef);
      if (byIdx && byIdx.element) return byIdx.element;
    } else if (messageRef.turnIndex !== undefined && messageRef.turnIndex !== null) {
      const byIdx = visible.find((m) => m.index === messageRef.turnIndex);
      if (byIdx && byIdx.element) return byIdx.element;
    }

    // 2. By content / snippet match
    const targetContent = (messageRef.content || messageRef.snippet || "").trim().toLowerCase();
    if (targetContent) {
      const searchSnippet = targetContent.slice(0, 80);
      const byContent = visible.find((m) => m.content && m.content.toLowerCase().includes(searchSnippet));
      if (byContent && byContent.element) return byContent.element;
    }

    return null;
  }

  scrollToMessage(messageRef) {
    if (messageRef === null || messageRef === undefined) return false;
    let el = this.findMessageElement(messageRef);

    if (!el || !document.body.contains(el)) return false;

    try {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("memory-layer-host-highlight");
      setTimeout(() => {
        el.classList.remove("memory-layer-host-highlight");
      }, 2200);
      return true;
    } catch (e) {
      return false;
    }
  }

  getConversationUrl(convId) {
    if (!convId) return "https://claude.ai/new";
    if (convId.startsWith("http://") || convId.startsWith("https://")) return convId;

    // Check if convId contains a verified UUID
    const uuidMatch = convId.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
    if (uuidMatch) {
      return `https://claude.ai/chat/${uuidMatch[1]}`;
    }
    // Fallback: safe root URL to avoid 404 on fabricated paths
    return "https://claude.ai/new";
  }

  navigateToConversation(convId, convUrl = null) {
    const targetUrl = convUrl || this.getConversationUrl(convId);
    if (targetUrl) {
      window.location.href = targetUrl;
      return true;
    }
    return false;
  }

  startNewChat() {
    const selectors = [
      'a[href="/new"]',
      'button[aria-label*="New chat"]'
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        el.click();
        return true;
      }
    }
    window.location.href = "https://claude.ai/new";
    return true;
  }
}

window.ClaudeAdapter = ClaudeAdapter;
