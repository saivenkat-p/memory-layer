"""
Verification test script for Milestone 8 Bulk History Import.
Runs Test 1, Test 2, Test 3, and Test 4 against an isolated test database (data/test_bulk_verification.db).
"""

import os
import json
import sys

from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.services.bulk_import import BulkImportEngine
from app.search.hybrid_search import HybridSearchEngine
from app.parsers.factory import parse_conversation_file


def run_suite():
    test_db_path = os.path.join("data", "test_bulk_verification.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    print("=" * 70)
    print("      MILESTONE 8 BULK HISTORY IMPORT VERIFICATION SUITE")
    print("=" * 70)
    print(f"Isolated Test DB Path: {os.path.abspath(test_db_path)}\n")

    db = Database(test_db_path)
    repo = ConversationRepository(db)
    bulk_engine = BulkImportEngine(repo)
    hybrid_search = HybridSearchEngine(repo)

    zip_path = os.path.join("data", "test_bulk_history.zip")
    with open(zip_path, "rb") as f:
        zip_bytes = f.read()

    # -------------------------------------------------------------------------
    # TEST 1: FIRST IMPORT
    # -------------------------------------------------------------------------
    print("--- TEST 1: FIRST BULK IMPORT ---")
    progress_log = []
    def p_cb(curr, tot, msg):
        progress_log.append(f"[{curr}/{tot}] {msg}")

    res1 = bulk_engine.import_archive_or_file(zip_bytes, "test_bulk_history.zip", progress_callback=p_cb)
    print(f"Conversations Detected : {res1.conversations_detected}")
    print(f"Conversations Imported : {res1.conversations_imported}")
    print(f"Duplicates Skipped    : {res1.duplicates_skipped}")
    print(f"Messages Imported     : {res1.messages_imported}")
    print(f"Embeddings Generated  : {res1.embeddings_generated}")
    print(f"Failures              : {res1.failures}")

    stats1 = repo.get_stats()
    emb_stats1 = hybrid_search.semantic_engine.get_embedding_statistics()
    print(f"DB Total Conversations : {stats1['total_conversations']}")
    print(f"DB Total Messages      : {stats1['total_messages']}")
    print(f"DB Total Embeddings    : {emb_stats1['total_embeddings']}\n")

    # -------------------------------------------------------------------------
    # TEST 2: DUPLICATE IMPORT
    # -------------------------------------------------------------------------
    print("--- TEST 2: DUPLICATE BULK IMPORT ---")
    res2 = bulk_engine.import_archive_or_file(zip_bytes, "test_bulk_history.zip", skip_duplicates=True)
    print(f"Conversations Detected : {res2.conversations_detected}")
    print(f"Conversations Imported : {res2.conversations_imported}")
    print(f"Duplicates Skipped    : {res2.duplicates_skipped}")

    stats2 = repo.get_stats()
    emb_stats2 = hybrid_search.semantic_engine.get_embedding_statistics()
    print(f"DB Total Conversations : {stats2['total_conversations']}")
    print(f"DB Total Messages      : {stats2['total_messages']}")
    print(f"DB Total Embeddings    : {emb_stats2['total_embeddings']}\n")

    # -------------------------------------------------------------------------
    # TEST 3: SEARCH ACROSS ALL THREE TOPICS
    # -------------------------------------------------------------------------
    print("--- TEST 3: HYBRID SEMANTIC SEARCH ACROSS IMPORTED CORPUS ---")
    test_queries = [
        ("the project about quantum circuits", "Quantum Computing with Qiskit"),
        ("the idea about automatically stopping the water motor", "Smart Water Tank IoT Monitoring Idea"),
        ("the project where I wanted to search my old AI conversations", "Personal AI Memory Layer Project"),
    ]

    search_success_count = 0
    for q_text, expected_title in test_queries:
        results = hybrid_search.search(q_text, limit=5)
        top_match = results[0] if results else None
        title = top_match.conversation_title if top_match else "NO MATCH"
        score = top_match.score if top_match else 0
        matched_snippet = top_match.snippet if top_match else ""

        print(f"Query         : \"{q_text}\"")
        print(f"Expected      : '{expected_title}'")
        print(f"Top Match     : '{title}' (Score: {score}%)")
        print(f"Snippet Preview: \"...{matched_snippet[:60]}...\"")

        if title == expected_title:
            search_success_count += 1
            print("  --> STATUS  : ✅ PASSED MATCH\n")
        else:
            print("  --> STATUS  : ❌ FAILED MATCH\n")

    # -------------------------------------------------------------------------
    # TEST 4: SINGLE IMPORT REGRESSION TEST
    # -------------------------------------------------------------------------
    print("--- TEST 4: SINGLE CONVERSATION IMPORT REGRESSION TEST ---")
    single_file_path = os.path.join("data", "sample_chat.txt")
    single_worked = False
    if os.path.exists(single_file_path):
        with open(single_file_path, "r", encoding="utf-8") as sf:
            single_txt = sf.read()
        single_conv = parse_conversation_file(single_txt, "sample_chat.txt")
        saved_id = repo.save_conversation(single_conv)
        fetched = repo.get_conversation(saved_id)
        if fetched and fetched.message_count > 0:
            single_worked = True
            print(f"Successfully imported single conversation '{fetched.title}' ({fetched.message_count} msgs)")
            print("  --> STATUS  : ✅ PASSED SINGLE IMPORT\n")

    print("=" * 70)
    print("                      VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_suite()
