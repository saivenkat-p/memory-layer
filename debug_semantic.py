"""
Diagnostic & Pipeline Tracing Script for Semantic and Hybrid Search.
"""

import os
import sys
import json
import numpy as np

from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine, ACTIVE_MODEL_NAME, EXPECTED_DIMENSION
from app.search.hybrid_search import HybridSearchEngine
from app.search.search_engine import SearchEngine


def debug():
    db_path = os.path.abspath(os.path.join("data", "memory.db"))
    print("=" * 70)
    print("      PERSONAL AI MEMORY LAYER — SEMANTIC PIPELINE DIAGNOSTIC")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # STEP 1: VERIFY EMBEDDING GENERATION & STORED DATABASE EMBEDDINGS
    # -------------------------------------------------------------------------
    print("\n--- STEP 1: DATABASE EMBEDDING INSPECTION ---")
    print(f"Database Path    : {db_path}")

    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found at {db_path}")
        sys.exit(1)

    db = Database(db_path)
    repo = ConversationRepository(db)
    semantic_engine = SemanticSearchEngine(repo)
    hybrid_engine = HybridSearchEngine(repo)

    print(f"Active Model Name: {semantic_engine.model_name}")
    print(f"Active Dimension : {EXPECTED_DIMENSION}")

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM message_embeddings")
        total_embeddings = cursor.fetchone()["total"]

        cursor.execute("SELECT model_name, embedding_json FROM message_embeddings")
        rows = cursor.fetchall()

    active_count = 0
    stale_count = 0
    invalid_count = 0

    for r in rows:
        m_name = r["model_name"]
        e_json = r["embedding_json"]
        if m_name == ACTIVE_MODEL_NAME:
            try:
                vec = json.loads(e_json)
                if len(vec) == EXPECTED_DIMENSION and np.all(np.isfinite(vec)):
                    active_count += 1
                else:
                    invalid_count += 1
            except Exception:
                invalid_count += 1
        else:
            stale_count += 1

    print(f"Total Stored Embeddings        : {total_embeddings}")
    print(f"Valid Active Model Embeddings  : {active_count}")
    print(f"Stale Model Embeddings         : {stale_count}")
    print(f"Invalid / Malformed Embeddings : {invalid_count}")

    # -------------------------------------------------------------------------
    # STEP 2: DIRECT SEMANTIC TEST AGAINST SOURCE TEXT
    # -------------------------------------------------------------------------
    print("\n--- STEP 2: DIRECT SEMANTIC TEST (ENCODER RAW COSINE SIMILARITY) ---")

    source_text = (
        "I don't want to climb the stairs to check whether the overhead tank is full. "
        "I want a system that shows the water level remotely and automatically stops the motor."
    )

    print(f"Source Text:\n\"{source_text}\"\n")

    source_vec = np.array(semantic_engine.generate_embedding(source_text), dtype=np.float32)

    queries = {
        "Q1": "Which idea did I have about not needing to physically inspect something?",
        "Q2": "I had an idea to prevent a household resource from being wasted because I didn't know its level.",
        "Q3": "That home automation idea about checking levels remotely",
    }

    raw_direct_sims = {}
    for q_id, q_text in queries.items():
        q_vec = np.array(semantic_engine.generate_embedding(q_text), dtype=np.float32)
        raw_sim = float(np.dot(source_vec, q_vec))
        raw_direct_sims[q_id] = raw_sim
        print(f"RAW DIRECT SIMILARITY ({q_id}): {raw_sim:.4f}")
        print(f"  Query: \"{q_text}\"\n")

    # -------------------------------------------------------------------------
    # STEP 3: TEST AGAINST ALL STORED MESSAGES IN DATABASE
    # -------------------------------------------------------------------------
    print("\n--- STEP 3: SEARCH ALL STORED MESSAGES IN SQLITE ---")

    for q_id, q_text in queries.items():
        print(f"\n=======================================================")
        print(f"QUERY [{q_id}]: \"{q_text}\"")
        print(f"=======================================================")

        top_semantic = semantic_engine.search_semantic(q_text, limit=10)

        print("\nTOP 10 SEMANTIC CANDIDATES FROM DATABASE:")
        for rank, (msg_id, sim_score) in enumerate(top_semantic, 1):
            # Fetch conversation info
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT m.content, m.msg_index, c.title, c.id as conv_id 
                    FROM messages m 
                    JOIN conversations c ON m.conversation_id = c.id 
                    WHERE m.id = ?
                    """,
                    (msg_id,),
                )
                r = cursor.fetchone()
            if r:
                title = r["title"]
                idx = r["msg_index"]
                snippet = r["content"][:80].replace("\n", " ")
                print(f"  Rank {rank:2d} | Sim: {sim_score:.4f} | [{title}] (Msg {idx}): \"{snippet}...\"")

        # -------------------------------------------------------------------------
        # STEP 4: CHECK CONFIGURATIONS AND THRESHOLDS
        # -------------------------------------------------------------------------
        print("\n--- STEP 4 & 5: PIPELINE TRACE & THRESHOLD CHECK ---")
        print(f"Configured Semantic Weight : {hybrid_engine.semantic_weight}")
        print(f"Configured Keyword Weight  : {hybrid_engine.keyword_weight}")
        print(f"Configured Min Threshold   : {hybrid_engine.min_relevance_threshold}")

        # Lexical keyword results
        kw_results = hybrid_engine.keyword_engine.search(q_text, limit=10)
        print(f"Keyword Matches Found      : {len(kw_results)}")
        for kr in kw_results[:3]:
            print(f"  Keyword Match: [{kr.conversation_title}] Raw Score: {kr.score}")

        # Top semantic candidate before threshold
        top_sem_before = top_semantic[0] if top_semantic else (None, 0.0)
        print(f"Top Semantic Score BEFORE threshold : {top_sem_before[1]:.4f}")

        # Hybrid results
        final_hybrid_results = hybrid_engine.search(q_text, limit=10)
        print(f"Final Hybrid Results AFTER threshold: {len(final_hybrid_results)}")
        for fr in final_hybrid_results:
            print(f"  --> Final Result: [{fr.conversation_title}] Final Score: {fr.score}%")

    print("\n" + "=" * 70)
    print("                       END OF DIAGNOSTIC")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    debug()
