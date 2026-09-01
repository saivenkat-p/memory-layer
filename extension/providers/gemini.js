/**
 * Gemini Provider Adapter (Milestone V6.2 Target Adapter).
 *
 * Implements robust DOM detection for Gemini (gemini.google.com):
 * - Multiple fallback selectors for Gemini prompt composer (Quill editor, rich-textarea, contenteditable, textarea)
 * - DOM title & active chat header inspection for current conversation title
 * - Reads currently visible webpage messages for DOM-based "Search This Conversation"
 */

class GeminiAdapter extends BaseProviderAdapter {
  constructor() {
    super();
    this.name = "Gemini";
  }

  isSupported() {
    return true; // Fully supported active implementation in V6.2
  }

  matchesPage() {
    return window.location.hostname.includes("gemini.google.com");
  }

  getCurrentConversationTitle() {
    // 1. Try document title (Gemini sets title like "Conversation Title - Gemini")
    if (document.title) {
      const docTitle = document.title
        .replace(/-\s*Gemini$/i, "")
        .replace(/\|\s*Gemini$/i, "")
        .replace(/^Gemini$/i, "")
        .trim();
      if (docTitle && docTitle !== "Gemini" && docTitle !== "New chat") {
        return docTitle;
      }
    }

    // 2. Try active sidebar / history title item or header
    const selectors = [
      'div[aria-selected="true"] .conversation-title',
      'a[aria-current="page"]',
      'button[aria-current="true"]',
      '.conversation-title',
      'header h1',
      'main h1'
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent) {
        const text = el.textContent.trim();
        if (text && text !== "Gemini" && text !== "New chat") {
          return text;
        }
      }
    }

    return "Gemini Conversation";
  }

  getComposer() {
    // Fallback Selector Strategy for Gemini DOM (rich-textarea, Quill editor, contenteditable, textarea)
    const selectors = [
      'rich-textarea div[contenteditable="true"]',
      'div.ql-editor[contenteditable="true"]',
      'div[contenteditable="true"][aria-label*="Prompt"]',
      'div[contenteditable="true"][aria-label*="Ask"]',
      'div[contenteditable="true"][aria-label*="Enter"]',
      'div[contenteditable="true"][role="textbox"]',
      '.input-area-container div[contenteditable="true"]',
      'div.input-area [contenteditable="true"]',
      'div[contenteditable="true"]',
      'textarea[aria-label*="Prompt"]',
      'textarea[placeholder*="Prompt"]',
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
    // Read visible user queries and Gemini model responses from page DOM
    const messageElements = document.querySelectorAll(
      'user-query, model-response, .user-query-container, .response-container-content, message-content, div[data-test-id="user-query"], div[data-test-id="model-response"], .query-text, .response-text'
    );

    const messages = [];
    messageElements.forEach((el, index) => {
      const tagName = el.tagName.toLowerCase();
      const testId = el.getAttribute("data-test-id") || "";
      const className = el.className || "";

      let role = "assistant";
      if (
        tagName === "user-query" ||
        testId.includes("user") ||
        className.includes("query") ||
        className.includes("user")
      ) {
        role = "user";
      }

      const textContent = el.textContent ? el.textContent.trim() : "";
      if (textContent) {
        messages.push({
          index,
          role,
          content: textContent,
          isDomVisible: true,
          element: el // Retain host element reference
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
    if (!convId) return "https://gemini.google.com/app";
    if (convId.startsWith("http://") || convId.startsWith("https://")) return convId;

    // Check if convId is a verified gemini id (e.g. gemini-16hex or 16hex)
    const geminiMatch = convId.match(/^gemini-([a-f0-9]{16,})$/i) || convId.match(/^([a-f0-9]{16,})$/i);
    if (geminiMatch) {
      return `https://gemini.google.com/app/${geminiMatch[1]}`;
    }
    // Fallback: safe root URL to avoid 404 on fabricated paths
    return "https://gemini.google.com/app";
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
      'button[data-test-id*="new-chat"]',
      'button[aria-label*="New chat"]',
      '.new-chat-button',
      'a[href="/app"]'
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && this._isElementVisible(el)) {
        el.click();
        return true;
      }
    }
    window.location.href = "https://gemini.google.com/app";
    return true;
  }
}

window.GeminiAdapter = GeminiAdapter;

