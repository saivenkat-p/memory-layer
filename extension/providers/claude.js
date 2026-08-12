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
}

window.ClaudeAdapter = ClaudeAdapter;
