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
          isDomVisible: true
        });
      }
    });

    return messages;
  }

  _isElementVisible(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }
}

window.GeminiAdapter = GeminiAdapter;

