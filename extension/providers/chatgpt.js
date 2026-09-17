/**
 * ChatGPT Provider Adapter (Milestone V6.1 Target Adapter).
 *
 * Implements robust DOM detection for ChatGPT (chatgpt.com / chat.openai.com):
 * - Multiple fallback selectors for the prompt composer (#prompt-textarea, [contenteditable="true"], textarea)
 * - DOM title & sidebar active link inspection for current conversation title
 * - Reads currently visible webpage messages for DOM-based "Search This Conversation"
 */

class ChatGPTAdapter extends BaseProviderAdapter {
  constructor() {
    super();
    this.name = "ChatGPT";
  }

  isSupported() {
    return true; // Fully supported active implementation
  }

  matchesPage() {
    const host = window.location.hostname;
    return host.includes("chatgpt.com") || host.includes("chat.openai.com");
  }

  getCurrentConversationTitle() {
    // 1. Try document title (ChatGPT updates page title to conversation title)
    const docTitle = document.title ? document.title.replace("- ChatGPT", "").trim() : "";
    if (docTitle && docTitle !== "ChatGPT" && docTitle !== "New chat") {
      return docTitle;
    }

    // 2. Try sidebar active link element
    const activeLink = document.querySelector('nav a[class*="bg-token-sidebar"], nav a[aria-current="page"]');
    if (activeLink && activeLink.textContent) {
      return activeLink.textContent.trim();
    }

    // 3. Fallback to header title
    const headerTitle = document.querySelector('h1, header div[class*="font-semibold"]');
    if (headerTitle && headerTitle.textContent) {
      return headerTitle.textContent.trim();
    }

    return "ChatGPT Conversation";
  }

  getCurrentConversationId() {
    const path = window.location.pathname;
    const match = path.match(/\/c\/([a-f0-9-]+)/i);
    if (match) {
      return match[1];
    }
    return null;
  }

  getComposer() {
    // Fallback Selector Strategy (Directive 7: Do not rely on one fragile selector)
    const selectors = [
      "#prompt-textarea",
      'div[contenteditable="true"][id="prompt-textarea"]',
      'div[contenteditable="true"]',
      'textarea[tabindex="0"]',
      'textarea[data-id]',
      'form textarea',
      'main form textarea',
      '[data-placeholder]',
      'textarea'
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && this._isElementVisible(el)) {
        return el;
      }
    }

    return null;
  }

  readVisibleMessages() {
    // Directive 4: Clear distinction between visible DOM messages vs backend indexed history
    const messageElements = document.querySelectorAll('article, div[data-message-author-role]');
    const messages = [];

    messageElements.forEach((el, index) => {
      const roleAttr = el.getAttribute("data-message-author-role");
      let role = "user";
      if (roleAttr === "assistant" || el.querySelector('[class*="agent-turn"]')) {
        role = "assistant";
      }

      const textContent = el.textContent ? el.textContent.trim() : "";
      if (textContent) {
        messages.push({
          index,
          role,
          content: textContent,
          isDomVisible: true,
          element: el // Retain host element reference for smooth scrolling & highlighting
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

    if (!el || !document.body.contains(el)) {
      console.warn("[ChatGPTAdapter] Target host message element is not currently mounted in DOM.");
      return false; // Graceful return if virtualized/unmounted
    }

    try {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("memory-layer-host-highlight");
      setTimeout(() => {
        el.classList.remove("memory-layer-host-highlight");
      }, 2200);
      return true;
    } catch (e) {
      console.error("[ChatGPTAdapter] Failed to scroll host message:", e);
      return false;
    }
  }

  getConversationUrl(convId) {
    if (!convId) return "https://chatgpt.com/";
    if (convId.startsWith("http://") || convId.startsWith("https://")) return convId;

    // Check if convId contains a verified UUID
    const uuidMatch = convId.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
    if (uuidMatch) {
      return `https://chatgpt.com/c/${uuidMatch[1]}`;
    }
    // Fallback: safe root URL to avoid 404 on fabricated paths
    return "https://chatgpt.com/";
  }

  navigateToConversation(convId, convUrl = null) {
    const targetUrl = convUrl || this.getConversationUrl(convId);
    if (targetUrl) {
      window.location.href = targetUrl;
      return true;
    }
    return false;
  }

  _isElementVisible(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }

  startNewChat() {
    const selectors = [
      'a[data-testid*="create-chat"]',
      'a[href="/"]',
      'button[aria-label*="New chat"]',
      'nav a[href="/"]'
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && this._isElementVisible(el)) {
        el.click();
        return true;
      }
    }
    window.location.href = "https://chatgpt.com/";
    return true;
  }
}

window.ChatGPTAdapter = ChatGPTAdapter;
