/**
 * Content Script for Personal AI Memory Layer Extension (Milestone V6.1 ChatGPT Target).
 *
 * Diagnostic & Mounting Enhancements:
 * 1. Checks user permission / activation gate (`chrome.storage.local`).
 * 2. Resolves active provider adapter (`ChatGPTAdapter`, `GeminiAdapter`, `ClaudeAdapter`).
 * 3. Injects floating `🧠 Memory Layer` trigger button on page load (independent of API status).
 * 4. Uses MutationObserver + polling to maintain button attachment across SPA DOM updates.
 * 5. Renders in-page Search & Context Overlay modal.
 * 6. Supports "Search This Conversation" (DOM visible messages vs backend indexed history).
 * 7. Supports "Search All AI Memory" global search.
 * 8. Safely inserts selected context into prompt composer (INSERT ONLY, NEVER auto-send).
 */

(async function () {
  console.log("[Memory Layer] Content script starting initialization on page:", window.location.href);

  const client = window.MemoryLayerClientInstance || new MemoryLayerClient();
  const manager = window.ContextManagerInstance || new ContextManager();

  // 1. Resolve Provider Adapter
  const adapters = [
    new ChatGPTAdapter(),
    new GeminiAdapter(),
    new ClaudeAdapter(),
  ];

  let currentAdapter = adapters.find((a) => a.matchesPage());
  if (!currentAdapter) {
    console.log("[Memory Layer] Current website is not a supported AI provider.");
    return;
  }

  console.log(`[Memory Layer] Matched provider adapter: ${currentAdapter.getProviderName()} (Supported: ${currentAdapter.isSupported()})`);

  // 2. Load Activation State (Defaults to true on first install)
  let isEnabled = await manager.loadActivationState();
  console.log(`[Memory Layer] Activation state loaded: isEnabled = ${isEnabled}`);

  // Listen for activation toggle messages from popup
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "MEMORY_LAYER_TOGGLED") {
      isEnabled = msg.enabled;
      console.log(`[Memory Layer] Received toggle update: isEnabled = ${isEnabled}`);
      if (isEnabled) {
        initMemoryLayerUI();
      } else {
        removeMemoryLayerUI();
      }
    }
  });

  if (isEnabled) {
    initMemoryLayerUI();
  }

  function removeMemoryLayerUI() {
    const existingBtn = document.getElementById("memory-layer-trigger-btn");
    if (existingBtn) existingBtn.remove();
    const existingOverlay = document.getElementById("memory-layer-overlay");
    if (existingOverlay) existingOverlay.remove();
  }

  function initMemoryLayerUI() {
    removeMemoryLayerUI();
    console.log("[Memory Layer] Initializing UI elements & DOM observer...");

    // Immediate attachment attempt
    ensureButtonAttached();

    // 1. Polling Fallback (500ms)
    const interval = setInterval(() => {
      if (!isEnabled) {
        clearInterval(interval);
        return;
      }
      ensureButtonAttached();
    }, 500);

    // 2. DOM MutationObserver
    const observer = new MutationObserver(() => {
      if (isEnabled) {
        ensureButtonAttached();
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  function ensureButtonAttached() {
    if (!isEnabled) return;
    if (document.getElementById("memory-layer-trigger-btn")) return;

    const composer = currentAdapter.getComposer();
    injectTriggerButton(composer);
  }

  function injectTriggerButton(composer) {
    if (document.getElementById("memory-layer-trigger-btn")) return;

    const btn = document.createElement("button");
    btn.id = "memory-layer-trigger-btn";
    btn.className = "memory-layer-floating-btn";
    btn.innerHTML = "🧠 Memory Layer";
    btn.type = "button";
    btn.title = "Open Personal AI Memory Layer Search & Context Overlay";

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      console.log("[Memory Layer] Trigger button clicked.");
      toggleOverlayModal();
    });

    // Attachment Strategy:
    // If composer is found, try injecting before or inside composer parent wrapper.
    // If no composer container found yet, attach directly to document.body (fixed bottom-right).
    if (composer) {
      const parentForm = composer.closest("form") || composer.parentElement;
      if (parentForm) {
        parentForm.appendChild(btn);
        console.log("[Memory Layer] Button attached near composer form.");
        return;
      }
    }

    // Fixed Fallback Attachment
    btn.classList.add("fixed-position");
    document.body.appendChild(btn);
    console.log("[Memory Layer] Button attached to document.body (fixed position fallback).");
  }

  function toggleOverlayModal() {
    let overlay = document.getElementById("memory-layer-overlay");
    if (overlay) {
      overlay.classList.toggle("hidden");
      return;
    }

    console.log("[Memory Layer] Creating in-page overlay drawer...");

    // Build Overlay Modal
    overlay = document.createElement("div");
    overlay.id = "memory-layer-overlay";
    overlay.className = "memory-layer-modal-overlay";

    overlay.innerHTML = `
      <div class="memory-layer-modal-container">
        <div class="memory-layer-modal-header">
          <div class="memory-layer-title">
            <span>🧠 Personal AI Memory Layer</span>
            <span class="provider-tag">${currentAdapter.getProviderName()}</span>
          </div>
          <button type="button" class="memory-layer-close-btn" id="ml-close-overlay">✕</button>
        </div>

        <div class="memory-layer-tabs">
          <button type="button" class="tab-btn active" id="tab-curr-conv">Search This Conversation</button>
          <button type="button" class="tab-btn" id="tab-all-mem">Search All AI Memory</button>
        </div>

        <div class="memory-layer-search-bar">
          <input type="text" id="ml-search-input" placeholder="Search memory context..." />
          <button type="button" id="ml-search-submit-btn">Search</button>
        </div>

        <div id="ml-conv-distinction-banner" class="memory-layer-banner">
          📌 <strong>Search Mode:</strong> Searching messages in <em>"${currentAdapter.getCurrentConversationTitle()}"</em>.
        </div>

        <div class="memory-layer-results-container" id="ml-results-list">
          <div class="memory-layer-placeholder">
            Enter a search term above to retrieve matched context blocks.
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Bind Modal Events
    document.getElementById("ml-close-overlay").addEventListener("click", () => {
      overlay.classList.add("hidden");
    });

    let activeMode = "current"; // 'current' or 'global'

    const tabCurr = document.getElementById("tab-curr-conv");
    const tabAll = document.getElementById("tab-all-mem");
    const banner = document.getElementById("ml-conv-distinction-banner");
    const searchInput = document.getElementById("ml-search-input");
    const searchBtn = document.getElementById("ml-search-submit-btn");

    tabCurr.addEventListener("click", () => {
      activeMode = "current";
      tabCurr.classList.add("active");
      tabAll.classList.remove("active");
      banner.style.display = "block";
      banner.innerHTML = `📌 <strong>Current Conversation Mode:</strong> Searching messages in <em>"${currentAdapter.getCurrentConversationTitle()}"</em>.`;
      executeSearch();
    });

    tabAll.addEventListener("click", () => {
      activeMode = "global";
      tabAll.classList.add("active");
      tabCurr.classList.remove("active");
      banner.style.display = "block";
      banner.innerHTML = `🌐 <strong>Global Memory Mode:</strong> Searching across all imported AI history in Memory Layer database.`;
      executeSearch();
    });

    searchBtn.addEventListener("click", executeSearch);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") executeSearch();
    });

    async function executeSearch() {
      const q = searchInput.value.trim();
      const resultsContainer = document.getElementById("ml-results-list");

      if (!q) {
        resultsContainer.innerHTML = `<div class="memory-layer-placeholder">Please enter a search query.</div>`;
        return;
      }

      resultsContainer.innerHTML = `<div class="memory-layer-placeholder">Searching Memory Layer backend...</div>`;

      if (activeMode === "current") {
        // Directive 4: Clear distinction between DOM visible messages vs backend history
        const domMsgs = currentAdapter.readVisibleMessages();
        const res = await client.searchGlobal(q, 10); // Search backend with query

        renderSearchResults(res, domMsgs, q);
      } else {
        const res = await client.searchGlobal(q, 15);
        renderSearchResults(res, [], q);
      }
    }

    function renderSearchResults(apiResponse, domMessages, queryText) {
      const container = document.getElementById("ml-results-list");

      if (apiResponse && apiResponse.offline) {
        container.innerHTML = `
          <div class="memory-layer-placeholder error-text">
            ⚠️ <strong>Memory Layer Backend Offline</strong><br>
            Could not connect to <code>http://127.0.0.1:8000</code>.<br>
            Launch the backend server using:<br>
            <code>python -m app.api.server</code>
          </div>
        `;
        return;
      }

      const backendResults = (apiResponse && apiResponse.results) ? apiResponse.results : [];

      if (!backendResults.length && !domMessages.length) {
        container.innerHTML = `<div class="memory-layer-placeholder">No matching memory items found for "${queryText}".</div>`;
        return;
      }

      let html = "";

      // DOM Messages section if matching
      const domMatches = domMessages.filter(m => m.content.toLowerCase().includes(queryText.toLowerCase()));
      if (domMatches.length > 0) {
        html += `<div class="results-section-header">📄 Page Messages Currently Visible (${domMatches.length})</div>`;
        domMatches.forEach((m) => {
          html += `
            <div class="memory-card dom-card">
              <div class="card-meta">
                <span class="role-badge ${m.role}">${m.role}</span>
                <span class="source-badge">Visible Webpage DOM</span>
              </div>
              <div class="card-content">${escapeHtml(m.content.slice(0, 250))}${m.content.length > 250 ? '...' : ''}</div>
              <div class="card-actions">
                <button type="button" class="insert-btn" data-text="${escapeAttr(m.content)}">📥 Insert into Prompt</button>
              </div>
            </div>
          `;
        });
      }

      // Backend Indexed History section
      if (backendResults.length > 0) {
        html += `<div class="results-section-header">🧠 Memory Layer Database Matches (${backendResults.length})</div>`;
        backendResults.forEach((r) => {
          const scoreStr = r.score ? `${r.score}%` : '';
          const snippet = r.snippet || r.matched_content || '';
          html += `
            <div class="memory-card">
              <div class="card-meta">
                <span class="role-badge ${r.matched_role}">${r.matched_role}</span>
                <span class="conv-title">${escapeHtml(r.conversation_title)}</span>
                <span class="provider-badge">${r.source}</span>
                ${scoreStr ? `<span class="score-badge">${scoreStr}</span>` : ''}
              </div>
              <div class="card-content">${escapeHtml(snippet)}</div>
              <div class="card-actions">
                <button type="button" class="insert-btn" data-text="${escapeAttr(r.matched_content || snippet)}">📥 Insert into Prompt</button>
              </div>
            </div>
          `;
        });
      }

      container.innerHTML = html;

      // Bind Insert Buttons (Directive 5: INSERT ONLY by default, NEVER auto-send)
      container.querySelectorAll(".insert-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const textToInsert = e.target.getAttribute("data-text");
          const inserted = currentAdapter.insertText(`[Memory Layer Reference Context]:\n${textToInsert}\n\n`);
          if (inserted) {
            btn.textContent = "✅ Inserted into Composer!";
            btn.style.backgroundColor = "#059669";
            setTimeout(() => {
              btn.textContent = "📥 Insert into Prompt";
              btn.style.backgroundColor = "";
            }, 2000);
          } else {
            alert("Could not locate composer text area. Please focus the chat prompt box and try again.");
          }
        });
      });
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
