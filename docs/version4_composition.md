# Version 4 — 🧩 Compose Context Documentation & Multi-Topic Retrieval System

## 1. Executive Summary & Product Vision

Version 4 introduces **Multi-Topic Context Composition & Decomposition** to the Personal AI Memory Layer.

The Memory Layer operates as a meta-layer positioned above individual AI conversation platforms:

```
                    PERSONAL AI MEMORY LAYER

       🧠 REMEMBER        🔍 FIND HERE       🌿 CONTINUE
            │                  │                  │
       ALL HISTORY          THIS CHAT         ONE TOPIC
            │                  │                  │
            └──────────────────┼──────────────────┘
                               ↓
                        🧩 COMPOSE CONTEXT
                               │
                 ┌─────────────┼─────────────┐
                 ↓             ↓             ↓
              Topic A       Topic B       Topic C
                 │             │             │
             ChatGPT        Gemini        Claude
                 └─────────────┼─────────────┘
                               ↓
                       SELECTED CONTEXT
                               ↓
                          PREVIEW / EDIT
                               ↓
                    COMPOSED CONVERSATION
                               ↓
                     [Future Version 5]
                               ↓
                  Choose AI destination
```

---

## 2. Multi-Topic Retrieval & Reranking Architecture

### 2.1 Topic Decomposition Algorithm ([`ContextComposer.decompose_query`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/app/services/context_composer.py))
When a complex composition query is entered:
`"Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."`

The decomposition engine extracts distinct topic components:
1. `Topic A`: `"Memory Layer"`
2. `Topic B`: `"funding strategy"`
3. `Topic C`: `"using it across ChatGPT Gemini"`

Each topic component is searched independently against the indexed memory corpus using `HybridSearchEngine`.

### 2.2 Parent vs Continuation Reranking & Metadata Inflation Protection
- **Keyword Scoring Fix**: Modified [`SearchEngine`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/app/search/search_engine.py) to calculate keyword counts primarily on the message content itself.
- **Derived Continuation Protection**: Titles starting with `"Continued:"` or `"Composed:"` are prohibited from multiplying metadata keyword matches, ensuring V3-derived continuation conversations do not crowd out their original parent conversations.
- **Original Parent Priority**: Candidate conversations are sorted such that original parent conversations (`is_derived = False`) are prioritized over derived continuations when relevances are comparable.

### 2.3 Diagnostic Metadata Engine
Search results include a `_diagnostics` payload providing complete inspectability:
- `query`: Raw user composition query string
- `detected_topics`: Array of extracted sub-topic strings
- `candidates_per_topic`: Map of candidate counts per topic
- `total_raw_candidates`: Total candidates retrieved before deduplication
- `duplicates_removed`: Number of duplicate message entries removed
- `conversations_found`: Total conversations containing candidates
- `providers_found`: Number of distinct AI providers (`ChatGPT`, `Gemini`, `Claude`)

---

## 3. Database Relationships & Provenance

- **`conversation_relationships` Table**: Supports multi-parent relationships using `relationship_type = 'context_composition'`. A single composed chat links back to **each** source parent conversation ($N \to 1$).
- **Message Provenance**: Derived messages store `source_conversation_id` and `source_message_id` attributes.
- **Immutability Guarantee**: Original conversations, messages, and vector embeddings remain 100% untouched.

---

## 4. Test Verification Summary

- **Baseline Tests**: 40 / 40 Passed.
- **Version 4 Composition Tests**: 16 / 16 Passed.
- **Total Regression Suite**: **56 / 56 Passed** (`Ran 56 tests in 1416.500s — OK`).
