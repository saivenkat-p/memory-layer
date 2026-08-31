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

  getComposer() {
    // Basic selector candidate for claude.ai
    return document.querySelector('div[contenteditable="true"], textarea');
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
