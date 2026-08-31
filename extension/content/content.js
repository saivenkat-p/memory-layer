/**
 * Content Script for Personal AI Memory Layer Extension (Cross-AI Context Bridge & Security Hardened V6.7).
 *
 * Implements the complete Cross-AI Context Bridge & Navigation UX:
 * 1. 🧠 Structured Memories tab (Decisions, Preferences, Facts, Project Goals).
 * 2. 💬 Raw Message Search tab (Global multi-turn conversation retrieval).
 * 3. 🔍 This Conversation tab (DOM visible messages vs backend history).
 * 4. Multi-Source Context Selection across conversations and providers.
 * 5. Destination Chooser (Current Chat, New Chat, Clipboard Copy).
 * 6. V6.4 2D Keyboard Navigation:
 *    - [← / →]: Cycle between distinct matching conversations
 *    - [↑ / ↓]: Navigate cards/occurrences within active list
 *    - [Esc]: Close overlay modal
 * 7. Pending Context Consumer on New Chat initiation (up to 10s resilient polling).
 * 8. Strict safety: INSERT ONLY (never auto-sends), local-only API (127.0.0.1:8000), XSS-safe, ID-only DOM references (no large data-text attributes).
 */

(async function () {
  console.log("[Memory Layer] Content script starting initialization on page:", window.location.href);

  const client = window.MemoryLayerClientInstance || new MemoryLayerClient();
  const manager = window.ContextManagerInstance || new ContextManager();
  const bridge = window.ContextBridgeInstance || new ContextBridge();

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

  // Consume any pending context from New Chat initiation (Cross-AI Bridge)
  bridge.checkAndConsumePendingContext(currentAdapter);

  // Initialize Opt-In Auto-Sync Engine (Milestone V6.2.x)
  const syncEngine = window.ConversationSyncEngineInstance;
  if (syncEngine) {
    syncEngine.init(currentAdapter);
  }

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
    const existingDestModal = document.getElementById("memory-layer-dest-modal");
    if (existingDestModal) existingDestModal.remove();
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
      if (!overlay.classList.contains("hidden")) {
        const input = document.getElementById("ml-search-input");
        if (input) input.focus();
      }
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
          <div class="header-nav-hints">
            <span class="nav-hint" title="Navigate between matched conversations">← / → Conv</span>
            <span class="nav-hint" title="Navigate cards within list">↑ / ↓ Card</span>
            <button type="button" class="memory-layer-close-btn" id="ml-close-overlay" title="Close (Esc)">✕</button>
          </div>
        </div>

        <div class="memory-layer-tabs">
          <button type="button" class="tab-btn active" id="tab-memories">🧠 Structured Memories</button>
          <button type="button" class="tab-btn" id="tab-all-mem">💬 Raw Message Search</button>
          <button type="button" class="tab-btn" id="tab-curr-conv">🔍 This Conversation</button>
        </div>

        <!-- Structured Memory Category Filter Chips -->
        <div class="memory-category-filter-bar" id="ml-category-filters">
          <button type="button" class="cat-chip active" data-type="all">🏷️ All</button>
          <button type="button" class="cat-chip chip-decision" data-type="decision">⚡ Decisions</button>
          <button type="button" class="cat-chip chip-preference" data-type="preference">⭐ Preferences</button>
          <button type="button" class="cat-chip chip-fact" data-type="fact">📌 Facts</button>
          <button type="button" class="cat-chip chip-goal" data-type="project_goal">🎯 Goals</button>
        </div>

        <div class="memory-layer-search-bar">
          <input type="text" id="ml-search-input" placeholder="Search structured memories (e.g., 'architecture', 'schedule', 'BM25')..." />
          <button type="button" id="ml-search-submit-btn">Search</button>
        </div>

        <div id="ml-conv-distinction-banner" class="memory-layer-banner">
          🧠 <strong>Structured Memory Mode:</strong> Querying high-value decisions, preferences, facts, and goals with exact provenance.
        </div>

        <div class="memory-layer-results-container" id="ml-results-list" tabindex="0">
          <div class="memory-layer-placeholder">
            Loading structured memories from Memory Layer...
          </div>
        </div>

        <!-- Multi-Selection Action Footer (Cross-AI Context Bridge) -->
        <div class="memory-selection-footer hidden" id="ml-selection-footer">
          <div class="selection-count-label" id="ml-selection-label">0 Items Selected</div>
          <div class="selection-actions">
            <button type="button" class="btn-clear-selection" id="ml-clear-selection-btn">Clear</button>
            <button type="button" class="btn-choose-dest" id="ml-choose-dest-btn">🎯 Apply to Destination...</button>
            <button type="button" class="btn-insert-selected" id="ml-insert-selected-btn">📥 Insert into Active Chat (0)</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // State Tracking
    let activeMode = "memories"; // 'memories' | 'global' | 'current'
    let activeCategory = "all"; // 'all' | 'decision' | 'preference' | 'fact' | 'project_goal'
    let currentCardIndex = -1;
    let currentConversationIndex = -1;
    let distinctConversationIds = [];

    // DOM Elements
    const tabMemories = document.getElementById("tab-memories");
    const tabAll = document.getElementById("tab-all-mem");
    const tabCurr = document.getElementById("tab-curr-conv");
    const categoryBar = document.getElementById("ml-category-filters");
    const banner = document.getElementById("ml-conv-distinction-banner");
    const searchInput = document.getElementById("ml-search-input");
    const searchBtn = document.getElementById("ml-search-submit-btn");
    const resultsContainer = document.getElementById("ml-results-list");
    const selectionFooter = document.getElementById("ml-selection-footer");
    const selectionLabel = document.getElementById("ml-selection-label");
    const insertSelectedBtn = document.getElementById("ml-insert-selected-btn");
    const chooseDestBtn = document.getElementById("ml-choose-dest-btn");
    const clearSelectionBtn = document.getElementById("ml-clear-selection-btn");

    // Close button
    document.getElementById("ml-close-overlay").addEventListener("click", () => {
      overlay.classList.add("hidden");
    });

    // Tab Event Handlers
    tabMemories.addEventListener("click", () => {
      activeMode = "memories";
      setActiveTab(tabMemories);
      categoryBar.style.display = "flex";
      banner.style.display = "block";
      banner.innerHTML = `🧠 <strong>Structured Memory Mode:</strong> Querying high-value decisions, preferences, facts, and goals with exact provenance.`;
      searchInput.placeholder = "Search structured memories (e.g., 'architecture', 'schedule', 'BM25')...";
      executeSearch();
    });

    tabAll.addEventListener("click", () => {
      activeMode = "global";
      setActiveTab(tabAll);
      categoryBar.style.display = "none";
      banner.style.display = "block";
      banner.innerHTML = `🌐 <strong>Global Raw Message Mode:</strong> Searching raw multi-turn conversation messages across entire database.`;
      searchInput.placeholder = "Search raw conversation transcripts...";
      executeSearch();
    });

    tabCurr.addEventListener("click", () => {
      activeMode = "current";
      setActiveTab(tabCurr);
      categoryBar.style.display = "none";
      banner.style.display = "block";
      banner.innerHTML = `📌 <strong>Current Conversation Mode:</strong> Searching messages in <em>"${escapeHtml(currentAdapter.getCurrentConversationTitle())}"</em>.`;
      searchInput.placeholder = "Search messages in this active chat...";
      executeSearch();
    });

    function setActiveTab(activeBtn) {
      [tabMemories, tabAll, tabCurr].forEach(btn => btn.classList.remove("active"));
      activeBtn.classList.add("active");
    }

    // Category Filter Chips
    categoryBar.querySelectorAll(".cat-chip").forEach(chip => {
      chip.addEventListener("click", (e) => {
        categoryBar.querySelectorAll(".cat-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        activeCategory = chip.getAttribute("data-type");
        executeSearch();
      });
    });

    // Search Execution
    searchBtn.addEventListener("click", executeSearch);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        executeSearch();
      }
    });

    // V6.4 2D Keyboard Navigation Listener
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const destModal = document.getElementById("memory-layer-dest-modal");
        if (destModal && !destModal.classList.contains("hidden")) {
          destModal.classList.add("hidden");
        } else {
          overlay.classList.add("hidden");
        }
        return;
      }

      const cards = Array.from(resultsContainer.querySelectorAll(".memory-card"));
      if (!cards.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        currentCardIndex = Math.min(currentCardIndex + 1, cards.length - 1);
        highlightCard(cards, currentCardIndex);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        currentCardIndex = Math.max(currentCardIndex - 1, 0);
        highlightCard(cards, currentCardIndex);
      } else if (e.key === "ArrowRight" && distinctConversationIds.length > 1) {
        e.preventDefault();
        currentConversationIndex = (currentConversationIndex + 1) % distinctConversationIds.length;
        jumpToConversationGroup(cards, distinctConversationIds[currentConversationIndex]);
      } else if (e.key === "ArrowLeft" && distinctConversationIds.length > 1) {
        e.preventDefault();
        currentConversationIndex = (currentConversationIndex - 1 + distinctConversationIds.length) % distinctConversationIds.length;
        jumpToConversationGroup(cards, distinctConversationIds[currentConversationIndex]);
      }
    });

    function highlightCard(cards, index) {
      cards.forEach(c => c.classList.remove("keyboard-focused"));
      if (index >= 0 && index < cards.length) {
        const target = cards[index];
        target.classList.add("keyboard-focused");
        target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }

    function jumpToConversationGroup(cards, convId) {
      const targetIndex = cards.findIndex(c => c.getAttribute("data-conv-id") === convId);
      if (targetIndex !== -1) {
        currentCardIndex = targetIndex;
        highlightCard(cards, currentCardIndex);
      }
    }

    // Initial load
    executeSearch();

    async function executeSearch() {
      const q = searchInput.value.trim();
      currentCardIndex = -1;
      currentConversationIndex = -1;
      distinctConversationIds = [];

      resultsContainer.innerHTML = `<div class="memory-layer-placeholder">Searching Memory Layer backend...</div>`;

      if (activeMode === "memories") {
        // Structured Memories Mode
        const typeFilter = activeCategory === "all" ? undefined : activeCategory;
        let res;
        if (q) {
          res = await client.searchMemories(q, { type: typeFilter, threshold: 0.30, hydrate: true });
        } else {
          const listRes = await client.listMemories({ type: typeFilter, status: "active", limit: 50, hydrate: true });
          res = {
            results: (listRes.memories || []).map(m => ({ memory: m, score: 1.0, source_messages: m.source_messages || [] })),
            offline: listRes.offline
          };
        }
        renderStructuredMemoryResults(res, q);
      } else if (activeMode === "current") {
        // In-Conversation Search Mode
        const domMsgs = currentAdapter.readVisibleMessages();
        const res = await client.searchGlobal(q || "", 15);
        renderRawSearchResults(res, domMsgs, q);
      } else {
        // Global Raw Messages Mode
        const res = await client.searchGlobal(q || "", 20);
        renderRawSearchResults(res, [], q);
      }
    }

    function renderStructuredMemoryResults(apiResponse, queryText) {
      if (apiResponse && apiResponse.offline) {
        renderOfflineNotice();
        return;
      }

      const results = (apiResponse && apiResponse.results) ? apiResponse.results : [];
      if (!results.length) {
        resultsContainer.innerHTML = `<div class="memory-layer-placeholder">No structured memories found${queryText ? ` matching "${escapeHtml(queryText)}"` : ""}.</div>`;
        return;
      }

      // Collect distinct conversation IDs for cross-conversation navigation
      const convSet = new Set();
      results.forEach(r => {
        if (r.memory && r.memory.conversation_id) convSet.add(r.memory.conversation_id);
      });
      distinctConversationIds = Array.from(convSet);

      let html = "";
      results.forEach((r, idx) => {
        const mem = r.memory;
        const memId = mem.id;
        const memType = mem.memory_type || "fact";
        const isChecked = bridge.hasItem(memId);
        const sourceMsgs = r.source_messages || mem.source_messages || [];
        const typeBadgeInfo = getTypeBadgeInfo(memType);

        html += `
          <div class="memory-card structured-card type-${memType}" data-id="${escapeAttr(memId)}" data-conv-id="${escapeAttr(mem.conversation_id)}" id="mem-card-${idx}">
            <div class="card-meta">
              <span class="type-badge ${typeBadgeInfo.cls}">${typeBadgeInfo.icon} ${typeBadgeInfo.label}</span>
              <span class="provider-badge">${escapeHtml(mem.provider || "Memory Layer")}</span>
              <span class="conv-title" title="Conversation: ${escapeAttr(mem.conversation_id)}">${escapeHtml(mem.conversation_id)}</span>
              ${r.score && r.score < 1.0 ? `<span class="score-badge">${Math.round(r.score * 100)}%</span>` : ""}
            </div>

            <div class="structured-claim-content">
              "${escapeHtml(mem.content)}"
            </div>

            <!-- Expandable Provenance Section -->
            <div class="provenance-section">
              <button type="button" class="btn-toggle-provenance" data-target="prov-${idx}">
                <span class="prov-arrow">▾</span> Provenance (${sourceMsgs.length} turn${sourceMsgs.length === 1 ? "" : "s"}) [Turns ${mem.start_msg_index}..${mem.end_msg_index}]
              </button>
              <div class="provenance-drawer hidden" id="prov-${idx}">
                ${renderProvenanceMessages(sourceMsgs, mem.start_msg_index)}
              </div>
            </div>

            <div class="card-actions">
              <label class="select-label">
                <input type="checkbox" class="mem-select-checkbox" data-id="${escapeAttr(memId)}" ${isChecked ? "checked" : ""}>
                <span>Select for Context</span>
              </label>
              <button type="button" class="insert-btn btn-insert-single" data-id="${escapeAttr(memId)}">📥 Insert Memory</button>
            </div>
          </div>
        `;
      });

      resultsContainer.innerHTML = html;

      // Bind Provenance Accordion Toggles
      resultsContainer.querySelectorAll(".btn-toggle-provenance").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          const targetId = btn.getAttribute("data-target");
          const drawer = document.getElementById(targetId);
          const arrow = btn.querySelector(".prov-arrow");
          if (drawer) {
            drawer.classList.toggle("hidden");
            if (arrow) arrow.textContent = drawer.classList.contains("hidden") ? "▾" : "▴";
          }
        });
      });

      // Bind Checkbox Selections (Bridge Integration)
      resultsContainer.querySelectorAll(".mem-select-checkbox").forEach(cb => {
        cb.addEventListener("change", (e) => {
          const memId = e.target.getAttribute("data-id");
          const match = results.find(r => r.memory.id === memId);
          if (e.target.checked && match) {
            bridge.addItem({
              id: memId,
              conversationId: match.memory.conversation_id,
              conversationTitle: match.memory.conversation_id,
              provider: match.memory.provider,
              role: "assistant",
              turnIndex: match.memory.start_msg_index,
              content: match.memory.content,
              memoryType: match.memory.memory_type
            });
          } else {
            bridge.removeItem(memId);
          }
          updateSelectionFooter();
        });
      });

      // Bind Single Insert Buttons (INSERT ONLY, NEVER AUTO-SEND)
      resultsContainer.querySelectorAll(".btn-insert-single").forEach(btn => {
        btn.addEventListener("click", (e) => {
          const memId = btn.getAttribute("data-id");
          const match = results.find(r => r.memory.id === memId);
          if (match && match.memory) {
            insertFormattedMemory(match.memory, btn);
          }
        });
      });
    }

    function renderProvenanceMessages(messages, startIdx) {
      if (!messages || !messages.length) {
        return `<div class="prov-empty">No raw message text stored for this provenance span.</div>`;
      }
      return messages.map((m, i) => {
        const turnIdx = m.index !== undefined ? m.index : (startIdx + i);
        const roleCls = m.role === "user" ? "user" : "assistant";
        const roleIcon = m.role === "user" ? "👤 User" : "🤖 Assistant";
        return `
          <div class="prov-turn ${roleCls}">
            <div class="prov-turn-header">
              <span class="prov-role-tag ${roleCls}">${roleIcon}</span>
              <span class="prov-turn-idx">Turn ${turnIdx}</span>
            </div>
            <div class="prov-turn-text">${escapeHtml(m.content)}</div>
          </div>
        `;
      }).join("");
    }

    function renderRawSearchResults(apiResponse, domMessages, queryText) {
      if (apiResponse && apiResponse.offline) {
        renderOfflineNotice();
        return;
      }

      const backendResults = (apiResponse && apiResponse.results) ? apiResponse.results : [];
      if (!backendResults.length && !domMessages.length) {
        resultsContainer.innerHTML = `<div class="memory-layer-placeholder">No matching raw messages found for "${escapeHtml(queryText)}".</div>`;
        return;
      }

      // Maintain in-memory item lookup map (V6.7 hardening: no large strings in DOM attributes)
      const rawItemsMap = new Map();

      // Collect distinct conversation IDs
      const convSet = new Set();
      backendResults.forEach(r => { if (r.conversation_id) convSet.add(r.conversation_id); });
      distinctConversationIds = Array.from(convSet);

      let html = "";

      // DOM Messages section
      const domMatches = domMessages.filter(m => m.content && m.content.toLowerCase().includes((queryText || "").toLowerCase()));
      if (domMatches.length > 0) {
        html += `<div class="results-section-header">📄 Visible Webpage DOM Messages (${domMatches.length})</div>`;
        domMatches.forEach((m, idx) => {
          const domId = `dom-msg-${m.index !== undefined ? m.index : idx}`;
          rawItemsMap.set(domId, {
            id: domId,
            conversationId: "current-webpage",
            conversationTitle: currentAdapter.getCurrentConversationTitle(),
            provider: currentAdapter.getProviderName(),
            role: m.role || "user",
            turnIndex: m.index !== undefined ? m.index : idx,
            content: m.content || ""
          });

          const isChecked = bridge.hasItem(domId);
          html += `
            <div class="memory-card dom-card" data-conv-id="current-page">
              <div class="card-meta">
                <span class="role-badge ${m.role}">${m.role}</span>
                <span class="source-badge">Active Webpage</span>
              </div>
              <div class="card-content">${escapeHtml(m.content.slice(0, 300))}${m.content.length > 300 ? "..." : ""}</div>
              <div class="card-actions">
                <label class="select-label">
                  <input type="checkbox" class="raw-select-checkbox" data-id="${escapeAttr(domId)}" ${isChecked ? "checked" : ""}>
                  <span>Select</span>
                </label>
                <button type="button" class="insert-btn raw-insert-btn" data-id="${escapeAttr(domId)}">📥 Insert into Prompt</button>
              </div>
            </div>
          `;
        });
      }

      // Backend Indexed History section
      if (backendResults.length > 0) {
        html += `<div class="results-section-header">🧠 Memory Layer Database Matches (${backendResults.length})</div>`;
        backendResults.forEach((r, idx) => {
          const scoreStr = r.score ? `${Math.round(r.score * 100)}%` : "";
          const snippet = r.snippet || r.matched_content || "";
          const rawId = r.matched_message_id || `raw-msg-${r.conversation_id}-${idx}`;
          rawItemsMap.set(rawId, {
            id: rawId,
            conversationId: r.conversation_id || "conv",
            conversationTitle: r.conversation_title || "Conversation",
            provider: r.source || "AI",
            role: r.matched_role || "assistant",
            turnIndex: r.matched_message_index !== undefined ? r.matched_message_index : idx,
            content: r.context_text || r.matched_content || snippet
          });

          const isChecked = bridge.hasItem(rawId);
          html += `
            <div class="memory-card" data-conv-id="${escapeAttr(r.conversation_id || "conv")}">
              <div class="card-meta">
                <span class="role-badge ${r.matched_role || "assistant"}">${r.matched_role || "msg"}</span>
                <span class="conv-title">${escapeHtml(r.conversation_title || "Conversation")}</span>
                <span class="provider-badge">${escapeHtml(r.source || "AI")}</span>
                ${scoreStr ? `<span class="score-badge">${scoreStr}</span>` : ""}
              </div>
              <div class="card-content">${escapeHtml(snippet)}</div>
              <div class="card-actions">
                <label class="select-label">
                  <input type="checkbox" class="raw-select-checkbox" data-id="${escapeAttr(rawId)}" ${isChecked ? "checked" : ""}>
                  <span>Select</span>
                </label>
                <button type="button" class="insert-btn raw-insert-btn" data-id="${escapeAttr(rawId)}">📥 Insert into Prompt</button>
              </div>
            </div>
          `;
        });
      }

      resultsContainer.innerHTML = html;

      // Bind Raw Checkbox Selections (Bridge Integration with In-Memory Lookup)
      resultsContainer.querySelectorAll(".raw-select-checkbox").forEach(cb => {
        cb.addEventListener("change", (e) => {
          const itemId = cb.getAttribute("data-id");
          const item = rawItemsMap.get(itemId);
          if (cb.checked && item) {
            bridge.addItem(item);
          } else {
            bridge.removeItem(itemId);
          }
          updateSelectionFooter();
        });
      });

      // Bind Raw Insert Buttons (INSERT ONLY, NEVER AUTO-SEND)
      resultsContainer.querySelectorAll(".raw-insert-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
          const itemId = btn.getAttribute("data-id");
          const item = rawItemsMap.get(itemId);
          if (item && item.content) {
            const inserted = currentAdapter.insertText(`[Memory Layer Reference Context]:\n${item.content}\n\n`);
            handleInsertFeedback(btn, inserted);
          }
        });
      });
    }

    function renderOfflineNotice() {
      resultsContainer.innerHTML = `
        <div class="memory-layer-placeholder error-text">
          ⚠️ <strong>Memory Layer Backend Offline</strong><br>
          Could not connect to <code>http://127.0.0.1:8000</code>.<br>
          Launch the backend server using:<br>
          <code>python -m app.api.server</code>
        </div>
      `;
    }

    function getTypeBadgeInfo(type) {
      switch (type) {
        case "decision":
          return { label: "DECISION", icon: "⚡", cls: "badge-decision" };
        case "preference":
          return { label: "PREFERENCE", icon: "⭐", cls: "badge-preference" };
        case "fact":
          return { label: "FACT", icon: "📌", cls: "badge-fact" };
        case "project_goal":
          return { label: "PROJECT GOAL", icon: "🎯", cls: "badge-goal" };
        default:
          return { label: (type || "MEMORY").toUpperCase(), icon: "🧠", cls: "badge-default" };
      }
    }

    function updateSelectionFooter() {
      const count = bridge.getCount();
      if (count > 0) {
        selectionFooter.classList.remove("hidden");
        selectionLabel.textContent = `${count} Item${count === 1 ? "" : "s"} Selected`;
        insertSelectedBtn.textContent = `📥 Insert into Active Chat (${count})`;
      } else {
        selectionFooter.classList.add("hidden");
      }
    }

    clearSelectionBtn.addEventListener("click", () => {
      bridge.clear();
      resultsContainer.querySelectorAll("input[type='checkbox']").forEach(cb => { cb.checked = false; });
      updateSelectionFooter();
    });

    insertSelectedBtn.addEventListener("click", () => {
      if (!bridge.getCount()) return;
      const formatted = bridge.formatContextPackage();
      const inserted = bridge.applyToCurrentChat(currentAdapter, formatted);
      handleInsertFeedback(insertSelectedBtn, inserted, `✅ Inserted ${bridge.getCount()} Items!`);
    });

    // =========================================================================
    // DESTINATION CHOOSER MODAL (CROSS-AI CONTEXT BRIDGE)
    // =========================================================================

    chooseDestBtn.addEventListener("click", () => {
      if (!bridge.getCount()) return;
      openDestinationChooserModal();
    });

    function openDestinationChooserModal() {
      let destModal = document.getElementById("memory-layer-dest-modal");
      if (!destModal) {
        destModal = document.createElement("div");
        destModal.id = "memory-layer-dest-modal";
        destModal.className = "memory-layer-modal-overlay dest-modal-layer";
        document.body.appendChild(destModal);
      }

      const count = bridge.getCount();
      const currentProvider = currentAdapter.getProviderName();
      const currentTitle = currentAdapter.getCurrentConversationTitle();

      destModal.innerHTML = `
        <div class="dest-chooser-container">
          <div class="dest-chooser-header">
            <h3>🎯 Cross-AI Destination Chooser</h3>
            <button type="button" class="memory-layer-close-btn" id="ml-close-dest-modal">✕</button>
          </div>

          <div class="dest-summary-banner">
            📦 <strong>Selected Context:</strong> ${count} item${count === 1 ? "" : "s"} ready to transfer.
          </div>

          <div class="dest-options-list">
            <label class="dest-option-card active">
              <input type="radio" name="ml_dest_choice" value="current" checked>
              <div class="dest-option-info">
                <div class="dest-option-title">💬 Apply to Active Chat</div>
                <div class="dest-option-desc">Inserts context directly into current composer: <em>"${escapeHtml(currentTitle)}"</em> on ${currentProvider}.</div>
              </div>
            </label>

            <label class="dest-option-card">
              <input type="radio" name="ml_dest_choice" value="new">
              <div class="dest-option-info">
                <div class="dest-option-title">✨ Start New Chat on ${currentProvider}</div>
                <div class="dest-option-desc">Opens a fresh conversation session and auto-injects the selected context package.</div>
              </div>
            </label>

            <label class="dest-option-card">
              <input type="radio" name="ml_dest_choice" value="copy">
              <div class="dest-option-info">
                <div class="dest-option-title">📋 Copy Context Package to Clipboard</div>
                <div class="dest-option-desc">Copies clean, formatted Markdown with provenance citations to paste across Claude, Gemini, or ChatGPT.</div>
              </div>
            </label>
          </div>

          <div class="dest-chooser-footer">
            <button type="button" class="btn-clear-selection" id="ml-cancel-dest-btn">Cancel</button>
            <button type="button" class="btn-apply-dest" id="ml-execute-dest-btn">🚀 Apply Context</button>
          </div>
        </div>
      `;

      destModal.classList.remove("hidden");

      // Bind Dest Modal Events
      document.getElementById("ml-close-dest-modal").addEventListener("click", () => {
        destModal.classList.add("hidden");
      });
      document.getElementById("ml-cancel-dest-btn").addEventListener("click", () => {
        destModal.classList.add("hidden");
      });

      destModal.querySelectorAll(".dest-option-card").forEach(card => {
        card.addEventListener("click", () => {
          destModal.querySelectorAll(".dest-option-card").forEach(c => c.classList.remove("active"));
          card.classList.add("active");
        });
      });

      document.getElementById("ml-execute-dest-btn").addEventListener("click", async () => {
        const selectedRadio = destModal.querySelector('input[name="ml_dest_choice"]:checked');
        const choice = selectedRadio ? selectedRadio.value : "current";
        const formatted = bridge.formatContextPackage();
        const executeBtn = document.getElementById("ml-execute-dest-btn");

        if (choice === "current") {
          const inserted = bridge.applyToCurrentChat(currentAdapter, formatted);
          destModal.classList.add("hidden");
          overlay.classList.add("hidden");
          if (inserted) {
            console.log("[ContextBridge] Context applied to active chat.");
          }
        } else if (choice === "new") {
          destModal.classList.add("hidden");
          overlay.classList.add("hidden");
          bridge.applyToNewChat(currentAdapter, formatted);
        } else if (choice === "copy") {
          const copied = await bridge.copyToClipboard(formatted);
          if (copied) {
            executeBtn.textContent = "✅ Copied to Clipboard!";
            setTimeout(() => {
              destModal.classList.add("hidden");
            }, 1200);
          }
        }
      });
    }

    function insertFormattedMemory(memory, btnElement) {
      const typeInfo = getTypeBadgeInfo(memory.memory_type);
      const formatted = `[Memory Layer Reference — ${typeInfo.label}]:\n"${memory.content}" (Source: ${memory.conversation_id})\n\n`;
      const inserted = currentAdapter.insertText(formatted);
      handleInsertFeedback(btnElement, inserted);
    }

    function handleInsertFeedback(btn, success, customSuccessText = "✅ Inserted into Composer!") {
      if (success) {
        const origText = btn.textContent;
        btn.textContent = customSuccessText;
        btn.style.backgroundColor = "#059669";
        setTimeout(() => {
          btn.textContent = origText;
          btn.style.backgroundColor = "";
        }, 2200);
      } else {
        alert("Could not locate composer text area. Please click into the chat prompt box and try again.");
      }
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
