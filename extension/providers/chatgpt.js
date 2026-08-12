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

window.ChatGPTAdapter = ChatGPTAdapter;
