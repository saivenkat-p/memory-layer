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

  getCurrentConversationId() {
    return null;
  }

  getComposer() {
    return null;
  }

  readVisibleMessages() {
    return [];
  }

  findMessageElement(messageMetadata) {
    if (!messageMetadata) return null;
    if (messageMetadata instanceof HTMLElement) return messageMetadata;
    if (messageMetadata.element instanceof HTMLElement) return messageMetadata.element;

    const visible = this.readVisibleMessages();
    // 1. Try turn index match
    if (messageMetadata.turnIndex !== undefined && messageMetadata.turnIndex !== null) {
      const byIdx = visible.find((m) => m.index === messageMetadata.turnIndex);
      if (byIdx && byIdx.element) return byIdx.element;
    }

    // 2. Try content snippet match
    const targetContent = (messageMetadata.content || messageMetadata.snippet || "").trim().toLowerCase();
    if (targetContent) {
      const searchSnippet = targetContent.slice(0, 80);
      const byContent = visible.find((m) => m.content && m.content.toLowerCase().includes(searchSnippet));
      if (byContent && byContent.element) return byContent.element;
    }

    return null;
  }

  scrollToMessage(messageRef) {
    if (!messageRef) return false;
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
    return null;
  }

  navigateToConversation(convId, convUrl = null) {
    const targetUrl = convUrl || this.getConversationUrl(convId);
    if (targetUrl) {
      window.location.href = targetUrl;
      return true;
    }
    return false;
  }
}

window.BaseProviderAdapter = BaseProviderAdapter;
