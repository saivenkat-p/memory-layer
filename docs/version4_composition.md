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
                    [V5A Portable Package]
                    schema_version: "1.0"
```

---

## 2. Multi-Topic Retrieval & Reranking Architecture

### 2.1 Topic Decomposition Engine ([`ContextComposer.decompose_query`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/app/services/context_composer.py))
When a complex composition query is entered:
`"Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."`

The decomposition engine extracts distinct topic components and clean search queries:
1. `Topic A`: `"Memory Layer"` (Search Query: `"Memory Layer"`)
2. `Topic B`: `"funding strategy"` (Search Query: `"funding strategy"`)
3. `Topic C`: `"ChatGPT Gemini"` (Search Query: `"ChatGPT Gemini"`)

Each topic component is searched independently against the indexed memory corpus using `HybridSearchEngine`.

### 2.2 Parent vs Continuation Overlap Suppression & Reranking
- **Overlap & Provenance Deduplication**: If a candidate message is from a derived continuation (`is_derived = True`) and its underlying content or `source_message_id` overlaps with an original parent candidate (`is_derived = False`), the continuation candidate is suppressed. This guarantees that V3 continuations do not crowd out original parent conversations.
- **Original Parent Priority**: Candidate conversations are sorted such that original parent conversations (`is_derived = False`) are prioritized before derived continuations when relevances are comparable.

### 2.3 Comprehensive 9-Point Diagnostic Engine
Search results include a detailed `_diagnostics` payload providing complete inspectability:
1. `original_query`: `"Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."`
2. `detected_topics`: `["Memory Layer", "funding strategy", "ChatGPT Gemini"]`
3. `search_queries`: `{"Memory Layer": "Memory Layer", "funding strategy": "funding strategy", "ChatGPT Gemini": "ChatGPT Gemini"}`
4. `candidates_per_topic`: `{"Memory Layer": 6, "funding strategy": 4, "ChatGPT Gemini": 4}`
5. `top_candidates_per_topic`: Summaries of top 3 candidates per topic.
6. `total_raw_candidates`: Total raw candidate count across all sub-topic searches (14).
7. `final_merged_candidates`: Count of unique candidates in the final candidate pool (12).
8. `duplicates_removed`: Count of duplicate message entries removed (3).
9. `parent_continuation_deduped`: Count of continuation messages suppressed due to parent overlap (1).
10. `diversity_reranking_decisions`: Prioritized original parent conversations and allocated candidates across 3 topic groups.

---

## 3. Database Relationships & Provenance

- **`conversation_relationships` Table**: Supports multi-parent relationships using `relationship_type = 'context_composition'`. A single composed chat links back to **each** source parent conversation ($N \to 1$).
- **Message Provenance**: Derived messages store `source_conversation_id` and `source_message_id` attributes.
- **Immutability Guarantee**: Original conversations, messages, and vector embeddings remain 100% untouched.

---

## 4. Test Verification Summary

- **Baseline Tests**: 56 / 56 Passed.
- **V5A Foundation Tests**: 10 / 10 Passed.
- **Total Regression Suite**: **66 / 66 Passed** (`Ran 66 tests in 87.717s — OK`).
