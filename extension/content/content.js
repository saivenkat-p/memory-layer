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
    const existingHUD = document.getElementById("ml-inspection-controller");
    if (existingHUD) existingHUD.remove();
  }

  async function initMemoryLayerUI() {
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

    // Check for active search session to resume Conversation Inspection Mode
    try {
      const activeSession = await bridge.loadSearchSession();
      if (activeSession && activeSession.active && activeSession.conversations && activeSession.conversations.length > 0) {
        const isFresh = activeSession.timestamp && (Date.now() - activeSession.timestamp < 2 * 60 * 60 * 1000);
        if (isFresh) {
          console.log("[Memory Layer] Resuming active search session in Conversation Inspection Mode:", activeSession);
          openConversationInspectionHUD(activeSession);
        }
      }
    } catch (e) {
      console.warn("[Memory Layer] Could not check active search session:", e);
    }
  }

  function ensureButtonAttached() {
    if (!isEnabled) return;
    if (document.getElementById("memory-layer-trigger-btn")) return;

    injectTriggerButton();
  }

  function injectTriggerButton() {
    if (document.getElementById("memory-layer-trigger-btn")) return;

    const btn = document.createElement("button");
    btn.id = "memory-layer-trigger-btn";
    btn.className = "memory-layer-floating-btn fixed-position";
    btn.innerHTML = "🧠 Memory Layer";
    btn.type = "button";
    btn.title = "Open Personal AI Memory Layer Search & Context Overlay";

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      console.log("[Memory Layer] Trigger button clicked.");
      toggleOverlayModal();
    });

    document.body.appendChild(btn);
    console.log("[Memory Layer] Button attached to document.body (guaranteed fixed position).");
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

        <!-- Multi-Selection Action Footer (Cross-AI Context Bridge & Topic Organization) -->
        <div class="memory-selection-footer hidden" id="ml-selection-footer">
          <div class="selection-count-label" id="ml-selection-label">0 Items Selected</div>
          <div class="selection-actions">
            <button type="button" class="btn-clear-selection" id="ml-clear-selection-btn">Clear</button>
            <button type="button" class="btn-focus-topic hidden" id="ml-topic-branch-btn">🎯 Focus Topic / Create Branch</button>
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
    const topicBranchBtn = document.getElementById("ml-topic-branch-btn");
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
      if (e.key === "Enter") executeSearch();
    });

    // Modal Keyboard Navigation Listener
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

      const cards = Array.from(resultsContainer.querySelectorAll(".conversation-card, .memory-card"));
      if (!cards.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        currentCardIndex = Math.min(currentCardIndex + 1, cards.length - 1);
        highlightModalCard(cards, currentCardIndex);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        currentCardIndex = Math.max(currentCardIndex - 1, 0);
        highlightModalCard(cards, currentCardIndex);
      } else if (e.key === "ArrowRight" && distinctConversationIds.length > 1) {
        e.preventDefault();
        currentConversationIndex = (currentConversationIndex + 1) % distinctConversationIds.length;
        jumpToConversationGroup(cards, distinctConversationIds[currentConversationIndex]);
      } else if (e.key === "ArrowLeft" && distinctConversationIds.length > 1) {
        e.preventDefault();
        currentConversationIndex = (currentConversationIndex - 1 + distinctConversationIds.length) % distinctConversationIds.length;
        jumpToConversationGroup(cards, distinctConversationIds[currentConversationIndex]);
      } else if (e.key === "Enter" && currentCardIndex >= 0 && currentCardIndex < cards.length) {
        const focused = cards[currentCardIndex];
        const openBtn = focused.querySelector(".btn-open-conv");
        if (openBtn) {
          e.preventDefault();
          openBtn.click();
        }
      }
    });

    function highlightModalCard(cards, index) {
      cards.forEach((c) => c.classList.remove("keyboard-focused"));
      if (index >= 0 && index < cards.length) {
        const target = cards[index];
        target.classList.add("keyboard-focused");
        target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }

    function jumpToConversationGroup(cards, convId) {
      const targetIndex = cards.findIndex((c) => c.getAttribute("data-conv-id") === convId);
      if (targetIndex !== -1) {
        currentCardIndex = targetIndex;
        highlightModalCard(cards, currentCardIndex);
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
            results: (listRes.memories || []).map((m) => ({ memory: m, score: 1.0, source_messages: m.source_messages || [] })),
            offline: listRes.offline
          };
        }
        renderStructuredMemoryResults(res, q);
      } else if (activeMode === "current") {
        // In-Conversation Search Mode: STRICTLY CURRENT CONVERSATION DOM ONLY
        const domMsgs = currentAdapter.readVisibleMessages();
        renderCurrentConversationResults(domMsgs, q);
      } else {
        // Global Raw Messages Mode: CHAT-CENTRIC GROUPING
        const res = await client.searchGlobal(q || "", 30);
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
      resultsContainer.querySelectorAll(".btn-toggle-provenance").forEach((btn) => {
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
      resultsContainer.querySelectorAll(".mem-select-checkbox").forEach((cb) => {
        cb.addEventListener("change", (e) => {
          const memId = e.target.getAttribute("data-id");
          const match = results.find((r) => r.memory.id === memId);
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
      resultsContainer.querySelectorAll(".btn-insert-single").forEach((btn) => {
        btn.addEventListener("click", () => {
          const memId = btn.getAttribute("data-id");
          const match = results.find((r) => r.memory.id === memId);
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

    function renderCurrentConversationResults(domMessages, queryText) {
      const qLower = (queryText || "").toLowerCase();
      const domMatches = (domMessages || []).filter((m) => !qLower || (m.content && m.content.toLowerCase().includes(qLower)));

      if (!domMatches.length) {
        resultsContainer.innerHTML = `<div class="memory-layer-placeholder">No matching messages found in this conversation for "${escapeHtml(queryText)}".</div>`;
        return;
      }

      distinctConversationIds = [];
      const rawItemsMap = new Map();
      let html = `<div class="results-section-header">📄 Visible Webpage Messages (${domMatches.length} match${domMatches.length === 1 ? "" : "es"})</div>`;

      domMatches.forEach((m, idx) => {
        const domId = `dom-msg-${m.index !== undefined ? m.index : idx}`;
        rawItemsMap.set(domId, {
          id: domId,
          conversationId: "current-webpage",
          conversationTitle: currentAdapter.getCurrentConversationTitle(),
          provider: currentAdapter.getProviderName(),
          role: m.role || "user",
          turnIndex: m.index !== undefined ? m.index : idx,
          content: m.content || "",
          element: m.element || null
        });

        const isChecked = bridge.hasItem(domId);
        html += `
          <div class="memory-card dom-card" data-conv-id="current-page" data-dom-index="${m.index !== undefined ? m.index : idx}">
            <div class="card-meta">
              <span class="role-badge ${m.role}">${m.role}</span>
              <span class="source-badge">Turn ${m.index !== undefined ? m.index : idx}</span>
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

      resultsContainer.innerHTML = html;

      // Event bindings
      resultsContainer.querySelectorAll(".raw-select-checkbox").forEach((cb) => {
        cb.addEventListener("change", (e) => {
          const id = e.target.getAttribute("data-id");
          const item = rawItemsMap.get(id);
          if (e.target.checked && item) {
            bridge.addItem(item);
          } else {
            bridge.removeItem(id);
          }
          updateSelectionFooter();
        });
      });

      resultsContainer.querySelectorAll(".raw-insert-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.getAttribute("data-id");
          const item = rawItemsMap.get(id);
          if (item) {
            const formatted = `[Memory Layer Reference — Turn ${item.turnIndex} (${item.role})]:\n"${item.content}"\n\n`;
            const inserted = currentAdapter.insertText(formatted);
            handleInsertFeedback(btn, inserted);
          }
        });
      });
    }

    // =========================================================================
    // 3. GLOBAL RAW MESSAGE SEARCH — CHAT-CENTRIC ARCHITECTURE
    // =========================================================================

    function renderRawSearchResults(apiResponse, domMessages, queryText) {
      if (apiResponse && apiResponse.offline) {
        renderOfflineNotice();
        return;
      }

      const backendResults = (apiResponse && apiResponse.results) ? apiResponse.results : [];
      if (!backendResults.length && !domMessages.length) {
        resultsContainer.innerHTML = `<div class="memory-layer-placeholder">No matching conversations found for "${escapeHtml(queryText)}".</div>`;
        return;
      }

      // Group all backend matches by conversation_id
      const convMap = new Map();

      backendResults.forEach((r, idx) => {
        const cid = r.conversation_id || `conv-${idx}`;
        if (!convMap.has(cid)) {
          convMap.set(cid, {
            conversationId: cid,
            conversationTitle: r.conversation_title || cid,
            provider: r.source || "AI",
            conversationUrl: r.conversation_url || null,
            score: r.score || 0,
            matches: []
          });
        }

        const entry = convMap.get(cid);
        if (r.score && r.score > entry.score) {
          entry.score = r.score;
        }

        entry.matches.push({
          messageId: r.matched_message_id || `raw-msg-${cid}-${idx}`,
          turnIndex: r.matched_message_index !== undefined ? r.matched_message_index : idx,
          role: r.matched_role || "assistant",
          content: r.context_text || r.matched_content || r.snippet || "",
          snippet: r.snippet || r.matched_content || "",
          score: r.score || 0
        });
      });

      const matchedConversations = Array.from(convMap.values());
      // Sort conversations by relevance score descending
      matchedConversations.sort((a, b) => b.score - a.score);

      let html = `<div class="results-section-header">💬 Matched Conversations (${matchedConversations.length})</div>`;

      matchedConversations.forEach((conv, cIdx) => {
        const scoreStr = conv.score ? `${Math.round(conv.score * 100)}% relevance` : "";
        const matchCountStr = `${conv.matches.length} matching occurrence${conv.matches.length === 1 ? "" : "s"}`;
        const providerIcon = getProviderIcon(conv.provider);

        // Preview of first 1-2 snippets
        const previewSnippets = conv.matches.slice(0, 2).map((m) => `
          <div class="conv-preview-item">
            <span class="conv-preview-role">[Turn ${m.turnIndex} ${m.role}]:</span>
            <span>"${escapeHtml(m.snippet || m.content.slice(0, 120))}"</span>
          </div>
        `).join("");

        html += `
          <div class="conversation-card" data-conv-index="${cIdx}" data-conv-id="${escapeAttr(conv.conversationId)}">
            <div class="conv-card-header">
              <div class="conv-card-title-group">
                <span class="conv-icon">📄</span>
                <span class="conv-card-title" title="${escapeAttr(conv.conversationTitle)}">${escapeHtml(conv.conversationTitle)}</span>
              </div>
              <div class="conv-card-badges">
                <span class="provider-badge">${providerIcon} ${escapeHtml(conv.provider)}</span>
                ${scoreStr ? `<span class="score-badge">${scoreStr}</span>` : ""}
                <span class="match-count-badge">${matchCountStr}</span>
              </div>
            </div>

            <div class="conv-card-preview">
              ${previewSnippets}
            </div>

            <div class="conv-card-actions">
              <button type="button" class="btn-open-conv" data-conv-index="${cIdx}">
                Open Conversation →
              </button>
            </div>
          </div>
        `;
      });

      resultsContainer.innerHTML = html;

      // Event listener for clicking conversation cards / Open Conversation
      resultsContainer.querySelectorAll(".conversation-card").forEach((card) => {
        card.addEventListener("click", async () => {
          const cIdx = parseInt(card.getAttribute("data-conv-index"), 10);
          if (isNaN(cIdx) || !matchedConversations[cIdx]) return;

          const targetConv = matchedConversations[cIdx];
          const session = {
            query: queryText,
            conversations: matchedConversations,
            currentConversationIndex: cIdx,
            currentOccurrenceIndex: 0,
            active: true,
            timestamp: Date.now()
          };

          // Save search session for persistence across navigation
          await bridge.saveSearchSession(session);

          // Hide global search modal
          overlay.classList.add("hidden");

          // Determine if destination is already active on current page
          const isSameChat = isCurrentPageMatch(targetConv);
          if (isSameChat) {
            openConversationInspectionHUD(session);
          } else {
            // Navigate to destination conversation
            const destUrl = getConversationDestinationUrl(targetConv);
            if (destUrl) {
              window.location.href = destUrl;
            } else {
              // Fallback to in-page inspection if no URL available
              openConversationInspectionHUD(session);
            }
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
        if (activeMode === "current") {
          topicBranchBtn.classList.remove("hidden");
        } else {
          topicBranchBtn.classList.add("hidden");
        }
      } else {
        selectionFooter.classList.add("hidden");
      }
    }

    clearSelectionBtn.addEventListener("click", () => {
      bridge.clear();
      resultsContainer.querySelectorAll("input[type='checkbox']").forEach(cb => { cb.checked = false; });
      updateSelectionFooter();
    });

    topicBranchBtn.addEventListener("click", () => {
      if (!bridge.getCount()) return;
      const currentTitle = currentAdapter.getCurrentConversationTitle();
      const currentConvId = window.location.pathname.split("/").filter(Boolean).pop() || "current-chat";
      const topicQuery = searchInput.value.trim() || "Focused Topic";
      const topicFormatted = bridge.formatTopicBranchPackage(currentTitle, currentConvId, topicQuery);
      openDestinationChooserModal(topicFormatted, `🎯 Topic Branch: "${escapeHtml(topicQuery)}"`);
    });

    insertSelectedBtn.addEventListener("click", () => {
      if (!bridge.getCount()) return;
      const formatted = bridge.formatContextPackage();
      const inserted = bridge.applyToCurrentChat(currentAdapter, formatted);
      handleInsertFeedback(insertSelectedBtn, inserted, `✅ Inserted ${bridge.getCount()} Items!`);
    });

    // =========================================================================
    // DESTINATION CHOOSER MODAL (CROSS-AI CONTEXT BRIDGE & TOPIC ORGANIZATION)
    // =========================================================================

    chooseDestBtn.addEventListener("click", () => {
      if (!bridge.getCount()) return;
      openDestinationChooserModal();
    });

    function insertFormattedMemory(memory, btnElement) {
      const typeInfo = getTypeBadgeInfo(memory.memory_type);
      const formatted = `[Memory Layer Reference — ${typeInfo.label}]:\n"${memory.content}" (Source: ${memory.conversation_id})\n\n`;
      const inserted = currentAdapter.insertText(formatted);
      handleInsertFeedback(btnElement, inserted);
    }
  }

  // =========================================================================
  // 4. FLOATING CONVERSATION INSPECTION CONTROLLER (HUD) & 2D NAVIGATION
  // =========================================================================

  let inspectionKeydownListener = null;

  async function openConversationInspectionHUD(session) {
    if (!session || !session.conversations || !session.conversations.length) return;

    let hud = document.getElementById("ml-inspection-controller");
    if (!hud) {
      hud = document.createElement("div");
      hud.id = "ml-inspection-controller";
      hud.className = "ml-inspection-controller";
      document.body.appendChild(hud);
    }
    hud.classList.remove("hidden");

    let convIdx = session.currentConversationIndex || 0;
    if (convIdx < 0 || convIdx >= session.conversations.length) convIdx = 0;

    const currentConv = session.conversations[convIdx];
    const matches = currentConv.matches || [];
    let occIdx = session.currentOccurrenceIndex || 0;
    if (occIdx < 0 || occIdx >= matches.length) occIdx = 0;

    const currentMatch = matches[occIdx] || {
      messageId: `msg-${convIdx}-${occIdx}`,
      turnIndex: occIdx,
      role: "assistant",
      content: "",
      snippet: ""
    };

    const isChecked = bridge.hasItem(currentMatch.messageId);
    const providerIcon = getProviderIcon(currentConv.provider);

    hud.innerHTML = `
      <div class="ml-inspect-header">
        <div class="ml-inspect-title">
          <span class="ml-inspect-icon">🔎</span>
          <span>Topic:</span>
          <span class="ml-inspect-query">"${escapeHtml(session.query || "Search")}"</span>
        </div>
        <div class="ml-inspect-actions">
          <button type="button" id="ml-reopen-search-btn" class="ml-btn-back" title="Back to Global Search Results">🔍 Results</button>
          <button type="button" id="ml-close-inspect-btn" class="ml-btn-close" title="Exit Inspection Mode (Esc)">✕</button>
        </div>
      </div>

      <div class="ml-inspect-body">
        <div class="ml-inspect-chat-info">
          <span class="ml-conv-tag">${providerIcon} ${escapeHtml(currentConv.provider)}</span>
          <strong class="ml-conv-name" title="${escapeAttr(currentConv.conversationTitle)}">${escapeHtml(currentConv.conversationTitle)}</strong>
        </div>

        <div class="ml-inspect-nav-bar">
          <!-- Conversation Navigation (<- / ->) -->
          <div class="ml-nav-group conv-nav">
            <button type="button" class="ml-nav-btn" id="ml-prev-conv-btn" title="Previous Matched Chat (←)" ${convIdx <= 0 ? "disabled" : ""}>← Prev Chat</button>
            <span class="ml-nav-counter">Chat ${convIdx + 1} / ${session.conversations.length}</span>
            <button type="button" class="ml-nav-btn" id="ml-next-conv-btn" title="Next Matched Chat (→)" ${convIdx >= session.conversations.length - 1 ? "disabled" : ""}>Next Chat →</button>
          </div>

          <!-- Occurrence Navigation (Up / Down) -->
          <div class="ml-nav-group occ-nav">
            <button type="button" class="ml-nav-btn" id="ml-prev-occ-btn" title="Previous Match (↑)" ${occIdx <= 0 ? "disabled" : ""}>↑ Prev Match</button>
            <span class="ml-nav-counter">Match ${occIdx + 1} / ${Math.max(matches.length, 1)}</span>
            <button type="button" class="ml-nav-btn" id="ml-next-occ-btn" title="Next Match (↓)" ${occIdx >= matches.length - 1 ? "disabled" : ""}>Next Match ↓</button>
          </div>
        </div>

        <!-- Occurrence Details Card -->
        <div class="ml-occurrence-card">
          <div class="ml-occ-meta">
            <span class="role-badge ${currentMatch.role || "assistant"}">${escapeHtml(currentMatch.role || "message")}</span>
            <span class="ml-turn-badge">Turn ${currentMatch.turnIndex !== undefined ? currentMatch.turnIndex : occIdx}</span>
            ${currentMatch.score ? `<span class="score-badge">${Math.round(currentMatch.score * 100)}%</span>` : ""}
          </div>
          <div class="ml-occ-text">${escapeHtml(currentMatch.snippet || currentMatch.content || "No message snippet available")}</div>
          <div class="ml-occ-actions">
            <label class="select-label">
              <input type="checkbox" id="ml-occ-checkbox" data-id="${escapeAttr(currentMatch.messageId)}" ${isChecked ? "checked" : ""}>
              <span>Select this message</span>
            </label>
            <button type="button" id="ml-occ-insert-btn" class="insert-btn">📥 Insert into Prompt</button>
            <button type="button" id="ml-occ-dest-btn" class="btn-choose-dest">🎯 Apply to Destination...</button>
          </div>
        </div>

        <div class="ml-2d-hints">
          <span><strong>↑ / ↓</strong>: Occurrences</span> • <span><strong>← / →</strong>: Matched Chats</span>
        </div>
      </div>
    `;

    // Highlight & smooth scroll active host message
    if (matches.length > 0) {
      currentAdapter.scrollToMessage(currentMatch);
    }

    // Bind HUD events
    document.getElementById("ml-close-inspect-btn").addEventListener("click", () => {
      hud.classList.add("hidden");
      session.active = false;
      bridge.saveSearchSession(session);
    });

    document.getElementById("ml-reopen-search-btn").addEventListener("click", () => {
      hud.classList.add("hidden");
      toggleOverlayModal(session.query, "global");
    });

    // Occurrence Navigation Buttons (↑ / ↓)
    const prevOccBtn = document.getElementById("ml-prev-occ-btn");
    const nextOccBtn = document.getElementById("ml-next-occ-btn");

    if (prevOccBtn) {
      prevOccBtn.addEventListener("click", () => {
        if (occIdx > 0) {
          session.currentOccurrenceIndex = occIdx - 1;
          bridge.saveSearchSession(session);
          openConversationInspectionHUD(session);
        }
      });
    }

    if (nextOccBtn) {
      nextOccBtn.addEventListener("click", () => {
        if (occIdx < matches.length - 1) {
          session.currentOccurrenceIndex = occIdx + 1;
          bridge.saveSearchSession(session);
          openConversationInspectionHUD(session);
        }
      });
    }

    // Conversation Navigation Buttons (← / →)
    const prevConvBtn = document.getElementById("ml-prev-conv-btn");
    const nextConvBtn = document.getElementById("ml-next-conv-btn");

    if (prevConvBtn) {
      prevConvBtn.addEventListener("click", () => {
        if (convIdx > 0) {
          navigateToSessionConversation(session, convIdx - 1);
        }
      });
    }

    if (nextConvBtn) {
      nextConvBtn.addEventListener("click", () => {
        if (convIdx < session.conversations.length - 1) {
          navigateToSessionConversation(session, convIdx + 1);
        }
      });
    }

    // Message Selection Checkbox
    const occCheckbox = document.getElementById("ml-occ-checkbox");
    if (occCheckbox) {
      occCheckbox.addEventListener("change", (e) => {
        if (e.target.checked) {
          bridge.addItem({
            id: currentMatch.messageId,
            conversationId: currentConv.conversationId,
            conversationTitle: currentConv.conversationTitle,
            provider: currentConv.provider,
            role: currentMatch.role || "assistant",
            turnIndex: currentMatch.turnIndex,
            content: currentMatch.content || currentMatch.snippet || ""
          });
        } else {
          bridge.removeItem(currentMatch.messageId);
        }
      });
    }

    // Message-Level Insert into Prompt Button (INSERT ONLY, NEVER AUTO-SEND)
    const insertBtn = document.getElementById("ml-occ-insert-btn");
    if (insertBtn) {
      insertBtn.addEventListener("click", () => {
        const textToInsert = currentMatch.content || currentMatch.snippet || "";
        if (textToInsert) {
          const formatted = `[Memory Layer Reference — Turn ${currentMatch.turnIndex} (${currentMatch.role})]:\n"${textToInsert}"\n\n`;
          const inserted = currentAdapter.insertText(formatted);
          handleInsertFeedback(insertBtn, inserted);
        }
      });
    }

    // Message-Level Apply to Destination Button
    const destBtn = document.getElementById("ml-occ-dest-btn");
    if (destBtn) {
      destBtn.addEventListener("click", () => {
        if (!bridge.hasItem(currentMatch.messageId)) {
          bridge.addItem({
            id: currentMatch.messageId,
            conversationId: currentConv.conversationId,
            conversationTitle: currentConv.conversationTitle,
            provider: currentConv.provider,
            role: currentMatch.role || "assistant",
            turnIndex: currentMatch.turnIndex,
            content: currentMatch.content || currentMatch.snippet || ""
          });
        }
        openDestinationChooserModal();
      });
    }

    // Attach 2D Keyboard Navigation Listener
    if (inspectionKeydownListener) {
      window.removeEventListener("keydown", inspectionKeydownListener);
    }

    inspectionKeydownListener = (e) => {
      // Don't intercept if user is typing in a textarea, input, or contenteditable
      const target = e.target;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }

      if (hud.classList.contains("hidden")) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (occIdx < matches.length - 1) {
          session.currentOccurrenceIndex = occIdx + 1;
          bridge.saveSearchSession(session);
          openConversationInspectionHUD(session);
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (occIdx > 0) {
          session.currentOccurrenceIndex = occIdx - 1;
          bridge.saveSearchSession(session);
          openConversationInspectionHUD(session);
        }
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (convIdx < session.conversations.length - 1) {
          navigateToSessionConversation(session, convIdx + 1);
        }
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (convIdx > 0) {
          navigateToSessionConversation(session, convIdx - 1);
        }
      } else if (e.key === "Escape") {
        hud.classList.add("hidden");
        session.active = false;
        bridge.saveSearchSession(session);
      }
    };

    window.addEventListener("keydown", inspectionKeydownListener);
  }

  async function navigateToSessionConversation(session, newConvIndex) {
    session.currentConversationIndex = newConvIndex;
    session.currentOccurrenceIndex = 0;
    session.active = true;
    session.timestamp = Date.now();
    await bridge.saveSearchSession(session);

    const targetConv = session.conversations[newConvIndex];
    if (isCurrentPageMatch(targetConv)) {
      openConversationInspectionHUD(session);
    } else {
      const destUrl = getConversationDestinationUrl(targetConv);
      if (destUrl) {
        window.location.href = destUrl;
      } else {
        openConversationInspectionHUD(session);
      }
    }
  }

  function isCurrentPageMatch(targetConv) {
    if (!targetConv) return false;
    const currentProvider = currentAdapter.getProviderName().toLowerCase();
    const targetProvider = (targetConv.provider || "").toLowerCase();
    if (!targetProvider.includes(currentProvider) && !currentProvider.includes(targetProvider)) {
      return false;
    }

    const currentTitle = currentAdapter.getCurrentConversationTitle().toLowerCase();
    const targetTitle = (targetConv.conversationTitle || "").toLowerCase();
    if (targetTitle && currentTitle && (currentTitle.includes(targetTitle) || targetTitle.includes(currentTitle))) {
      return true;
    }

    const currentUrl = window.location.href;
    if (targetConv.conversationId && currentUrl.includes(targetConv.conversationId)) {
      return true;
    }

    return false;
  }

  function getConversationDestinationUrl(conv) {
    if (!conv) return null;
    if (conv.conversationUrl && (conv.conversationUrl.startsWith("http://") || conv.conversationUrl.startsWith("https://"))) {
      return conv.conversationUrl;
    }
    const provider = (conv.provider || "").toLowerCase();
    const cid = conv.conversationId || "";

    if (provider.includes("chatgpt") || provider.includes("openai")) {
      const uuidMatch = cid.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
      return uuidMatch ? `https://chatgpt.com/c/${uuidMatch[1]}` : "https://chatgpt.com/";
    }
    if (provider.includes("gemini") || provider.includes("google")) {
      const hexMatch = cid.match(/^gemini-([a-f0-9]{16,})$/i) || cid.match(/^([a-f0-9]{16,})$/i);
      return hexMatch ? `https://gemini.google.com/app/${hexMatch[1]}` : "https://gemini.google.com/app";
    }
    if (provider.includes("claude") || provider.includes("anthropic")) {
      const uuidMatch = cid.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
      return uuidMatch ? `https://claude.ai/chat/${uuidMatch[1]}` : "https://claude.ai/new";
    }
    return null;
  }

  function getProviderIcon(provider) {
    const p = (provider || "").toLowerCase();
    if (p.includes("chatgpt") || p.includes("openai")) return "🤖";
    if (p.includes("gemini") || p.includes("google")) return "✨";
    if (p.includes("claude") || p.includes("anthropic")) return "🧠";
    return "🌐";
  }

  // =========================================================================
  // 5. DESTINATION CHOOSER MODAL (CROSS-AI CONTEXT BRIDGE)
  // =========================================================================

  function openDestinationChooserModal(customFormatted = null, customBannerText = null) {
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
    const formatted = customFormatted || bridge.formatContextPackage();
    const bannerContent = customBannerText
      ? `🎯 <strong>${customBannerText}</strong> — ${count} turn${count === 1 ? "" : "s"} staged for derived branch.`
      : `📦 <strong>Selected Context:</strong> ${count} item${count === 1 ? "" : "s"} ready to transfer.`;

    // Determine alternate supported AI providers
    const alternateProviders = [];
    if (currentProvider !== "ChatGPT") {
      alternateProviders.push({ key: "chatgpt", name: "ChatGPT", host: "chatgpt.com" });
    }
    if (currentProvider !== "Claude") {
      alternateProviders.push({ key: "claude", name: "Claude", host: "claude.ai" });
    }
    if (currentProvider !== "Gemini") {
      alternateProviders.push({ key: "gemini", name: "Gemini", host: "gemini.google.com" });
    }

    const altOptionsHtml = alternateProviders.map((p) => `
      <label class="dest-option-card">
        <input type="radio" name="ml_dest_choice" value="alt_${p.key}">
        <div class="dest-option-info">
          <div class="dest-option-title">✨ Open in ${p.name} (${p.host})</div>
          <div class="dest-option-desc">Opens ${p.name} in a new tab with staged context ready for insertion.</div>
        </div>
      </label>
    `).join("");

    destModal.innerHTML = `
      <div class="dest-chooser-container">
        <div class="dest-chooser-header">
          <h3>🎯 Cross-AI Destination Chooser</h3>
          <button type="button" class="memory-layer-close-btn" id="ml-close-dest-modal">✕</button>
        </div>

        <div class="dest-summary-banner">
          ${bannerContent}
        </div>

        <!-- Exact Context Preview Accordion -->
        <div class="dest-preview-toggle" id="ml-toggle-preview">
          <span>👁️ Preview Formatted Context (${count} items)</span>
          <span id="ml-preview-arrow">▾</span>
        </div>
        <pre class="dest-preview-box hidden" id="ml-preview-box">${escapeHtml(formatted)}</pre>

        <div class="dest-options-list">
          <label class="dest-option-card active">
            <input type="radio" name="ml_dest_choice" value="current" checked>
            <div class="dest-option-info">
              <div class="dest-option-title">💬 Apply to Active Chat (${currentProvider})</div>
              <div class="dest-option-desc">Inserts context directly into current composer: <em>"${escapeHtml(currentTitle)}"</em>.</div>
            </div>
          </label>

          <label class="dest-option-card">
            <input type="radio" name="ml_dest_choice" value="new">
            <div class="dest-option-info">
              <div class="dest-option-title">✨ Start New Chat on ${currentProvider}</div>
              <div class="dest-option-desc">Opens a fresh conversation session on ${currentProvider} and auto-injects context.</div>
            </div>
          </label>

          ${altOptionsHtml}

          <label class="dest-option-card">
            <input type="radio" name="ml_dest_choice" value="copy">
            <div class="dest-option-info">
              <div class="dest-option-title">📋 Copy Context Package to Clipboard</div>
              <div class="dest-option-desc">Copies clean, formatted Markdown with provenance citations to paste across any AI tool.</div>
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

    // Bind Preview Toggle
    const previewToggle = document.getElementById("ml-toggle-preview");
    const previewBox = document.getElementById("ml-preview-box");
    const previewArrow = document.getElementById("ml-preview-arrow");

    if (previewToggle && previewBox && previewArrow) {
      previewToggle.addEventListener("click", () => {
        const isHidden = previewBox.classList.contains("hidden");
        if (isHidden) {
          previewBox.classList.remove("hidden");
          previewArrow.textContent = "▴";
        } else {
          previewBox.classList.add("hidden");
          previewArrow.textContent = "▾";
        }
      });
    }

    // Bind Dest Modal Events
    document.getElementById("ml-close-dest-modal").addEventListener("click", () => {
      destModal.classList.add("hidden");
    });
    document.getElementById("ml-cancel-dest-btn").addEventListener("click", () => {
      destModal.classList.add("hidden");
    });

    destModal.querySelectorAll(".dest-option-card").forEach((card) => {
      card.addEventListener("click", () => {
        destModal.querySelectorAll(".dest-option-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        const radio = card.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
      });
    });

    document.getElementById("ml-execute-dest-btn").addEventListener("click", async () => {
      const selectedRadio = destModal.querySelector('input[name="ml_dest_choice"]:checked');
      const choice = selectedRadio ? selectedRadio.value : "current";
      const executeBtn = document.getElementById("ml-execute-dest-btn");
      const overlay = document.getElementById("memory-layer-overlay");

      if (choice === "current") {
        const inserted = bridge.applyToCurrentChat(currentAdapter, formatted);
        destModal.classList.add("hidden");
        if (overlay) overlay.classList.add("hidden");
        if (inserted) {
          console.log("[ContextBridge] Context applied to active chat.");
        }
      } else if (choice === "new") {
        destModal.classList.add("hidden");
        if (overlay) overlay.classList.add("hidden");
        bridge.applyToNewChat(currentAdapter, formatted);
      } else if (choice.startsWith("alt_")) {
        const targetKey = choice.replace("alt_", "");
        destModal.classList.add("hidden");
        if (overlay) overlay.classList.add("hidden");
        await bridge.applyToAlternateProvider(targetKey, formatted);
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

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();

