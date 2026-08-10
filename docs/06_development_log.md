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
- **Acceptance Verification**:
  - Tested zero-vocabulary-overlap queries:
    - `"The idea where I don't have to physically go upstairs to inspect something."` -> Matches Water Tank!
    - `"A way to remotely know whether a household resource has enough supply."` -> Matches Water Tank!
    - `"Automatically prevent overflow without manually checking the tank."` -> Matches Water Tank!
    - `"Quantum entanglement circuit."` -> Water Tank NOT returned.
    - `"Qiskit quantum circuit."` -> Qiskit returned.
    - `"Childhood cricket memories."` -> No relevant water-tank result.
