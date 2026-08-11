# Development Log — Personal AI Memory Layer

## Log Entry 1: Initial MVP (Milestones 1–7)
- Built project structure, conversation schemas (`Message`, `Conversation`), and strategy parsers (`JSONParser`, `TXTParser`).
- Built SQLite storage (`conversations`, `messages`).
- Implemented keyword search with SQL `LIKE` conditions.
- Implemented Source Context viewer showing target message alongside previous and following messages.
- Implemented `Ask My Memory` assistant grounded in retrieved source messages.

---

## Log Entry 2: Evaluation of First "LocalVectorEngine" & Discovery of Limitation
- **Evaluation**: The initial `LocalVectorEngine` in `app/search/semantic_search.py` used word frequencies, bigrams, and character trigrams.
- **Finding**: It performed **lexical n-gram vector matching** rather than true neural semantic embedding retrieval.
- **Real User Testing Failure**:
  - Source: *"I don't want to climb the stairs to check whether the overhead tank is full."*
  - Query: *"The idea where I don't have to go upstairs to inspect something"* -> **0 Results**.
  - Query: *"A system that lets me remotely know whether a household resource is sufficient."* -> **0 Results**.
- **Root Cause**: Because the query used completely different vocabulary ("upstairs", "inspect", "remotely", "household resource") than the source text ("climb the stairs", "check overhead tank"), the n-gram vector inner product was `0.0`.

---

## Log Entry 3: Evolution to Real Local Neural Semantic Search
- **Architectural Revision**: Replaced `LocalVectorEngine` with a true local pretrained transformer model: `sentence-transformers` (`all-MiniLM-L6-v2`, 384 dimensions).
- **Persistence**: Persisted 384-dimensional dense vectors in SQLite `message_embeddings` table.
- **Hybrid Fusion**: Fused keyword score ($w=0.3$) and neural cosine similarity score ($w=0.7$) with a minimum relevance threshold of $0.35$.

---

## Log Entry 4: Database Embedding Migration & Stale Vector Lifecycle Fix
- **Problem Discovered**: Pre-existing SQLite database (`data/memory.db`) contained legacy embeddings from the previous lexical implementation (`model_name = "local-vector-v1"`). When `SemanticSearchEngine` ran, silent exception handling (`except Exception: continue`) caused pre-existing data to produce zero semantic search results.
- **Model Version Awareness**:
  - Implemented `model_name` validation in `SemanticSearchEngine.validate_stored_embedding()`.
  - Stale embeddings (`model_name != "all-MiniLM-L6-v2"`) are flagged, skipped, and logged with diagnostic warnings.
- **Re-indexing Engine & CLI Tool**:
  - Implemented `reindex_all_embeddings()` in `app/search/semantic_search.py`.
  - Created `reindex_embeddings.py` CLI script to regenerate embeddings for pre-existing database files.
  - Successfully re-indexed `data/memory.db`: 6 conversations, 24 messages re-indexed with 0 failures.
- **Error Reporting**:
  - Removed silent `except Exception: pass` swallows in repository saving. Errors during embedding generation are explicitly logged and raised.
- **Empirical Acceptance Verification**:
  - All 30 unit & integration tests passed.
  - Verified zero-vocabulary-overlap queries:
    - `"The idea where I don't have to go upstairs to inspect something"` -> **Smart Water Tank Monitoring System (54%)**
    - `"A system that lets me remotely know whether a household resource is sufficient."` -> **Smart Water Tank Monitoring System (65%)**
    - `"Automatically prevent overflow without manually checking the tank."` -> **Smart Water Tank Monitoring System (60%)**
    - `"I need to remotely monitor household supply without physically inspecting it."` -> **Smart Water Tank Monitoring System (65%)**
    - `"Quantum entanglement circuit."` -> **No sufficiently relevant memory found.**
    - `"Childhood cricket memories."` -> **No sufficiently relevant memory found.**

---

## Log Entry 5: Milestone 8 — Bulk History Import System
- **Problem Solved**: Users accumulate hundreds of conversations across AI platforms and cannot manually locate individual conversations to upload. V1 requires bulk history ingestion.
- **Multi-Format Extraction**:
  - Extended `JSONParser` with `parse_bulk()` for ChatGPT `conversations.json` exports.
  - Created `BulkParser` in `app/parsers/bulk_parser.py` for extracting `.zip` archives containing multiple JSON/TXT files in memory.
- **Duplicate Prevention**:
  - Added `is_duplicate()` and `find_duplicate_id()` to `ConversationRepository` using title + message count + content snippet fingerprinting.
- **Bulk Import Engine & Progress Reporting**:
  - Created `BulkImportEngine` in `app/services/bulk_import.py` to manage multi-file parsing, duplicate filtering, batch DB saves, progress callbacks, and metric reporting (`BulkImportResult`).
- **Streamlit UI Upgrade**:
  - Upgraded **📥 Import History** tab in `app/main.py` with dual mode (`📦 Bulk History Import` vs `📄 Single Conversation File`).
  - Added real-time progress indicators (`327 / 1,248 conversations`) and import summary report cards.
- **Automated Tests**:
  - Created `tests/test_bulk_import.py` (4 new tests, 34 total tests passing cleanly).

---

## Log Entry 6: Version 3 — 🔍 Find Here & 🌿 Continue Topic
- **Problem Solved**:
  - *Find Here*: Users know a topic was discussed inside a specific long conversation, but scrolling hundreds of messages is painful. Searching must be ephemeral without polluting database history.
  - *Continue Topic*: Users want to extract a single topic from a multi-topic conversation and create a focused conversation.
- **Feature 1: 🔍 Find Here**:
  - Implemented `FindHereEngine` in `app/search/find_here.py`.
  - Scopes hybrid (keyword + neural vector) search strictly to `conversation_id = ?`.
  - Ephemeral guarantee: Search queries execute in-memory and are never inserted into database messages or persistent vector embeddings.
  - UI: Integrated match snippet cards and **Jump to Match** context display in Streamlit.
- **Feature 2: 🌿 Continue Topic**:
  - Implemented `TopicExtractionEngine` in `app/services/topic_extractor.py`.
  - Scores target messages using local `all-MiniLM-L6-v2` neural similarity, groups user/assistant pairs, and maintains strict chronological sequence ($80 \to 84 \to 91$).
  - Message provenance: Derived continuation messages record `source_conversation_id` and `source_message_id` references to avoid redundant embedding generation.
  - Added `conversation_relationships` table to `app/repositories/database.py` (`id`, `parent_conversation_id`, `child_conversation_id`, `relationship_type`, `topic`, `created_at`).
  - UI: Integrated interactive context preview and **Create Focused Continuation Chat** workflow.
- **Automated Tests**:
  - Created `tests/test_version3_features.py` (6 new tests).
  - Executed complete regression suite: **40 / 40 tests PASSED**.

---

## Log Entry 7: Version 4 — 🧩 Compose Context & Multi-Topic Retrieval System Fixes
- **Problem Solved & Retrieval Fixes**:
  - Multi-topic queries like `"Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."` initially suffered from single-clause dominance and V3 continuation title keyword inflation.
  - Multi-Topic Query Decomposition: `ContextComposer.decompose_query()` splits complex prompts into distinct sub-topics and searches each independently against the indexed memory corpus.
  - Parent vs Continuation Reranking: Fixed `SearchEngine` keyword score calculation to count keywords on message content instead of concatenated metadata strings, preventing derived continuations (`Continued:...`) from crowding out parent conversations.
  - Diagnostics Metadata: Implemented `_diagnostics` payload tracking query, detected sub-topics, per-topic candidate counts, raw semantic scores, keyword scores, and deduplication stats.
- **Context Composition Engine (`ContextComposer`)**:
  - Multi-topic hybrid search groups candidates by source conversation and AI provider.
  - Selection, deselection, reordering (↑/↓/✕), and preview generation.
  - Multi-parent relationships: Derived composed chat links back to each parent conversation via `relationship_type = 'context_composition'`.
  - Provenance & Immutability: `source_conversation_id` and `source_message_id` references preserved. Source data remains 100% untouched.
  - Destination Architecture: Implemented `ComposedContext.export()` for future Version 5 AI destination handoffs.
- **Streamlit UI**:
  - Added `🧩 Compose Context` navigation view to `app/main.py`.
  - Step 1: Multi-topic search input & grouped candidate checkboxes.
  - Step 2: Expandable **🔍 View Multi-Topic Diagnostics & Ranking Breakdown** panel.
  - Step 3: Interactive context preview with Move Up (↑), Move Down (↓), and Remove (✕) controls.
  - Step 4: Composed chat creation & toast notification.
- **Automated Tests & Regression Suite**:
  - Created `tests/test_version4_composition.py` (16 tests including multi-topic decomposition, candidate deduplication, and parent vs continuation reranking).
  - Executed full regression test suite: **56 / 56 tests PASSED** (`Ran 56 tests in 1416.500s — OK`).
