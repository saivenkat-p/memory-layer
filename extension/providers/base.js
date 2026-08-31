/**
 * Base AI Provider Adapter Interface.
 * Defines the contract that all website-specific adapters (ChatGPT, Gemini, Claude) must implement.
 */

class BaseProviderAdapter {
  constructor() {
    this.name = "BaseProvider";
  }

  getProviderName() {
    return this.name;
  }

  isSupported() {
    return false;
  }

  matchesPage() {
    return false;
  }

  getCurrentConversationTitle() {
    return "Unknown Conversation";
  }

  getComposer() {
    return null;
  }

  readVisibleMessages() {
    return [];
  }

  insertText(text) {
    const composer = this.getComposer();
    if (!composer) return false;
    return window.PromptInjector.insertTextIntoComposer(composer, text);
  }

  startNewChat() {
    return false;
  }
}

window.BaseProviderAdapter = BaseProviderAdapter;
