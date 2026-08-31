/**
 * Injection Utility safely inserting text into target AI prompt composers (ChatGPT, Gemini, Claude).
 *
 * CRITICAL SAFETY RULES:
 * 1. INSERT ONLY by default.
 * 2. NEVER automatically trigger or click Send/Submit buttons.
 * 3. Uses modern InputEvent and Selection/Range APIs with property descriptor fallbacks.
 * 4. Compatible with React 18, Lexical, ProseMirror, and Quill rich-text editors.
 */

class PromptInjector {
  static insertTextIntoComposer(targetElement, textToInsert) {
    if (!targetElement) {
      console.warn("[PromptInjector] Target composer element is null.");
      return false;
    }

    if (!textToInsert) {
      return true;
    }

    try {
      targetElement.focus();

      // 1. Standard <textarea> or <input> elements
      if (targetElement.tagName === "TEXTAREA" || targetElement.tagName === "INPUT") {
        const start = targetElement.selectionStart !== null ? targetElement.selectionStart : targetElement.value.length;
        const end = targetElement.selectionEnd !== null ? targetElement.selectionEnd : targetElement.value.length;
        const currentVal = targetElement.value || "";

        const newVal = currentVal.substring(0, start) + textToInsert + currentVal.substring(end);

        // Use native value descriptor setter if available for React state synchronization
        const prototype = targetElement.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
        if (descriptor && descriptor.set) {
          descriptor.set.call(targetElement, newVal);
        } else {
          targetElement.value = newVal;
        }

        // Dispatch synthetic InputEvent and change event
        targetElement.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: textToInsert }));
        targetElement.dispatchEvent(new Event("change", { bubbles: true }));

        const newCursorPos = start + textToInsert.length;
        if (typeof targetElement.setSelectionRange === "function") {
          targetElement.setSelectionRange(newCursorPos, newCursorPos);
        }
        return true;
      }

      // 2. Modern [contenteditable="true"] rich-text elements (ChatGPT Lexical, Gemini Quill, Claude ProseMirror)
      if (targetElement.isContentEditable || targetElement.getAttribute("contenteditable") === "true") {
        // Step A: Dispatch beforeinput event
        try {
          const beforeInput = new InputEvent("beforeinput", {
            bubbles: true,
            cancelable: true,
            inputType: "insertText",
            data: textToInsert
          });
          targetElement.dispatchEvent(beforeInput);
        } catch (e) {
          // Ignore beforeinput errors in legacy environments
        }

        // Step B: Insert via Selection Range API
        let inserted = false;
        try {
          const sel = window.getSelection();
          if (sel && sel.rangeCount > 0) {
            const range = sel.getRangeAt(0);
            range.deleteContents();
            const textNode = document.createTextNode(textToInsert);
            range.insertNode(textNode);
            range.setStartAfter(textNode);
            range.setEndAfter(textNode);
            sel.removeAllRanges();
            sel.addRange(range);
            inserted = true;
          }
        } catch (rangeErr) {
          console.warn("[PromptInjector] Range insertion failed, trying execCommand fallback:", rangeErr);
        }

        // Step C: Fallback to document.execCommand if Range was not available
        if (!inserted && typeof document.execCommand === "function") {
          try {
            inserted = document.execCommand("insertText", false, textToInsert);
          } catch (e) {
            // Ignore execCommand deprecation errors
          }
        }

        // Step D: Final DOM fallback
        if (!inserted) {
          const p = document.createElement("p");
          p.textContent = textToInsert;
          targetElement.appendChild(p);
        }

        // Step E: Dispatch input and change events to trigger React/ProseMirror state reconciliation
        try {
          targetElement.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: textToInsert }));
        } catch (e) {
          targetElement.dispatchEvent(new Event("input", { bubbles: true }));
        }
        targetElement.dispatchEvent(new Event("change", { bubbles: true }));
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
