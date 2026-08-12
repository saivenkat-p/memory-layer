/**
 * Injection Utility safely inserting text into target AI prompt composers.
 *
 * CRITICAL SAFETY RULES (Directive 5):
 * 1. INSERT ONLY by default.
 * 2. NEVER automatically trigger or click Send buttons.
 * 3. Dispatches native React/DOM events to update composer state cleanly.
 */

class PromptInjector {
  static insertTextIntoComposer(targetElement, textToInsert) {
    if (!targetElement) {
      console.warn("[PromptInjector] Target composer element is null.");
      return false;
    }

    try {
      targetElement.focus();

      // Handle standard <textarea> or <input>
      if (targetElement.tagName === "TEXTAREA" || targetElement.tagName === "INPUT") {
        const start = targetElement.selectionStart || 0;
        const end = targetElement.selectionEnd || 0;
        const currentVal = targetElement.value || "";

        const newVal = currentVal.substring(0, start) + textToInsert + currentVal.substring(end);
        targetElement.value = newVal;

        // Dispatch input and change events for React/Vue dynamic listeners
        targetElement.dispatchEvent(new Event("input", { bubbles: true }));
        targetElement.dispatchEvent(new Event("change", { bubbles: true }));

        // Move cursor to end of inserted text
        const newCursorPos = start + textToInsert.length;
        targetElement.setSelectionRange(newCursorPos, newCursorPos);
        return true;
      }

      // Handle [contenteditable="true"] elements (ChatGPT modern DOM)
      if (targetElement.isContentEditable) {
        // Method 1: Using execCommand (most reliable across browser React contenteditables)
        const success = document.execCommand("insertText", false, textToInsert);
        if (success) {
          targetElement.dispatchEvent(new Event("input", { bubbles: true }));
          return true;
        }

        // Fallback Method 2: Appending text node
        const p = document.createElement("p");
        p.textContent = textToInsert;
        targetElement.appendChild(p);
        targetElement.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      }

      console.warn("[PromptInjector] Unsupported composer element type:", targetElement);
      return false;
    } catch (e) {
      console.error("[PromptInjector] Error inserting text:", e);
      return false;
    }
  }
}

window.PromptInjector = PromptInjector;
