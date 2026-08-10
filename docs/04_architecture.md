# Architecture Documentation — Personal AI Memory Layer

## 1. System Overview

The **Personal AI Memory Layer** turns imported AI conversation exports (ChatGPT, Gemini, Claude, Perplexity) and chat transcripts into a searchable, privacy-focused personal knowledge base.

Core philosophy:
> *"Don't make users remember WHERE they discussed something. Let them search for WHAT they remember discussing."*

---

## 2. Component Architecture

```
                                  User Query
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
        Keyword Search                                Semantic Search
   (SQL Full-Text & Term Match)                  (Local Neural Embeddings)
               │                                             │
               │                                   Query Vector Encoding
               │                                 (all-MiniLM-L6-v2, 384d)
               │                                             │
               │                                  Cosine Similarity Search
               │                                (SQLite message_embeddings)
               │                                             │
               └──────────────────────┬──────────────────────┘
                                      ▼
                             Hybrid Ranking Fusion
             S_final = 0.7 * S_semantic + 0.3 * S_keyword_norm
                                      │
                                      ▼
                        Relevance Thresholding (≥ 0.35)
                                      │
                                      ▼
                            Ranked Source Context
```

---

## 3. Data Storage & Vector Persistence

### SQLite Database (`data/memory.db`)

1. **`conversations`**:
   - `id` (PRIMARY KEY)
   - `title`, `source`, `imported_at`, `original_date`, `category`, `tags`, `description`

2. **`messages`**:
   - `id` (PRIMARY KEY)
   - `conversation_id` (FOREIGN KEY -> conversations.id ON DELETE CASCADE)
   - `role`, `content`, `msg_index`, `timestamp`

3. **`message_embeddings`**:
   - `message_id` (PRIMARY KEY, FOREIGN KEY -> messages.id ON DELETE CASCADE)
   - `embedding_json` (384-dimensional dense float vector string/array)
   - `model_name` (`"all-MiniLM-L6-v2"`)
   - `updated_at` (ISO 8601 timestamp)

---

## 4. Semantic Search & Hybrid Ranking

### Local Neural Embedding Model
- **Model**: `all-MiniLM-L6-v2` via `sentence-transformers`.
- **Dimensions**: 384 float values per text vector.
- **Privacy & Security**: Runs 100% locally on CPU. No conversation text is sent to cloud APIs.

### Hybrid Fusion & Thresholding
- **Normalized Keyword Score** $S_{\text{keyword\_norm}} \in [0, 1]$
- **Semantic Cosine Similarity** $S_{\text{semantic}} \in [0, 1]$
- **Final Hybrid Score**:
  $$S_{\text{final}} = 0.7 \cdot S_{\text{semantic}} + 0.3 \cdot S_{\text{keyword\_norm}}$$
- **Relevance Threshold**: $S_{\text{final}} \ge 0.35$. If no candidate exceeds $0.35$, the search returns *"No sufficiently relevant memory found."*
