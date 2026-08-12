/**
 * Gemini Provider Adapter (Structured Stub — Planned for V6.6).
 *
 * NOTE: As per Directive 3, this adapter is a structured stub until manually verified.
 */

class GeminiAdapter extends BaseProviderAdapter {
  constructor() {
    super();
    this.name = "Gemini";
  }

  isSupported() {
    return false; // Stub until V6.6 manual verification
  }

  matchesPage() {
    return window.location.hostname.includes("gemini.google.com");
  }

  getCurrentConversationTitle() {
    return "Gemini Conversation";
  }

  getComposer() {
    // Basic selector candidate for gemini.google.com
    return document.querySelector('.input-area, [contenteditable="true"], textarea');
  }
}

window.GeminiAdapter = GeminiAdapter;
