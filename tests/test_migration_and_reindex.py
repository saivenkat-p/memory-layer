"""
Unit & Integration Test Suite for Embedding Migration, Versioning, and Re-indexing.
"""

import unittest
import os
import json
import gc
from datetime import datetime, timezone

from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine, ACTIVE_MODEL_NAME
from app.search.hybrid_search import HybridSearchEngine


class TestEmbeddingMigrationAndReindex(unittest.TestCase):

    def setUp(self):
        self.db = Database(":memory:")
        self.repo = ConversationRepository(self.db)
        self.semantic_engine = SemanticSearchEngine(self.repo)
        self.hybrid_engine = HybridSearchEngine(self.repo)

    # Test A: New conversation creates all-MiniLM-L6-v2 embeddings
    def test_A_new_conversation_creates_active_embeddings(self):
        conv = Conversation(
            title="Active Model Test",
            messages=[Message(role="user", content="Solar panel inverter system.", index=0)],
        )
        self.repo.save_conversation(conv)

        msg_id = conv.messages[0].id
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT model_name, embedding_json FROM message_embeddings WHERE message_id = ?", (msg_id,))
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["model_name"], ACTIVE_MODEL_NAME)
        vec = json.loads(row["embedding_json"])
        self.assertEqual(len(vec), 384)

    # Test B: Old local-vector-v1 embeddings detected as stale
    def test_B_old_local_vector_v1_detected_as_stale(self):
        stale_json = json.dumps({"water": 0.5, "tank": 0.8})
        is_valid, reason, _ = self.semantic_engine.validate_stored_embedding(stale_json, "local-vector-v1")
        
        self.assertFalse(is_valid)
        self.assertIn("Stale model name", reason)

    # Test C: Re-index replaces stale embeddings
    def test_C_reindex_replaces_stale_embeddings(self):
        conv = Conversation(
            title="Stale Migration Test",
            messages=[Message(role="user", content="Overhead tank water level motor control.", index=0)],
        )
        self.repo.save_conversation(conv)
        msg_id = conv.messages[0].id

        # Manually overwrite with stale local-vector-v1 row
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE message_embeddings SET model_name = 'local-vector-v1', embedding_json = ? WHERE message_id = ?",
                (json.dumps({"stale": 1.0}), msg_id)
            )
            conn.commit()

        # Verify it is stale
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT model_name FROM message_embeddings WHERE message_id = ?", (msg_id,))
            self.assertEqual(cursor.fetchone()["model_name"], "local-vector-v1")

        # Run reindex
        stats = self.semantic_engine.reindex_all_embeddings()
        self.assertGreater(stats["embeddings_reindexed"], 0)

        # Verify updated to active model
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT model_name, embedding_json FROM message_embeddings WHERE message_id = ?", (msg_id,))
            row = cursor.fetchone()
            self.assertEqual(row["model_name"], ACTIVE_MODEL_NAME)
            vec = json.loads(row["embedding_json"])
            self.assertEqual(len(vec), 384)

    # Test D: Search works after re-indexing
    def test_D_search_works_after_reindexing(self):
        conv = Conversation(
            title="Post Reindex Search Test",
            messages=[Message(role="user", content="Rainwater harvesting collection cistern.", index=0)],
        )
        self.repo.save_conversation(conv)
        self.semantic_engine.reindex_all_embeddings()

        results = self.hybrid_engine.search("rainwater storage tank")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Post Reindex Search Test")

    # Test E: Database survives application restart
    def test_E_database_survives_restart(self):
        db_file = os.path.abspath("data/test_migration_restart.db")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass

        db1 = Database(db_file)
        repo1 = ConversationRepository(db1)
        conv = Conversation(
            title="Restart Persistence Test",
            messages=[Message(role="user", content="Battery energy storage system.", index=0)],
        )
        repo1.save_conversation(conv)

        # Simulating restart
        db2 = Database(db_file)
        repo2 = ConversationRepository(db2)
        engine2 = HybridSearchEngine(repo2)

        results = engine2.search("battery energy storage")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Restart Persistence Test")

        del repo1, repo2, db1, db2, engine2
        gc.collect()
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass

    # Test F: Invalid embedding data does not crash application
    def test_F_invalid_embedding_data_graceful_handling(self):
        conv = Conversation(
            title="Corrupt Data Test",
            messages=[Message(role="user", content="Testing corrupt vector handling.", index=0)],
        )
        self.repo.save_conversation(conv)
        msg_id = conv.messages[0].id

        # Insert corrupt JSON into message_embeddings
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE message_embeddings SET embedding_json = 'INVALID_JSON_CORRUPT' WHERE message_id = ?",
                (msg_id,)
            )
            conn.commit()

        # Search should complete without raising exception
        results = self.hybrid_engine.search("Testing corrupt vector handling")
        self.assertIsInstance(results, list)

    # Test G: Semantic query with zero vocabulary overlap retrieves water tank conversation
    def test_G_zero_vocabulary_overlap_semantic_retrieval(self):
        conv = Conversation(
            title="Smart Water Tank Monitoring System",
            source="ChatGPT",
            messages=[
                Message(
                    role="user",
                    content="I don't want to climb the stairs to check whether the overhead tank is full. I want a system that shows the water level remotely and automatically stops the motor.",
                    index=0,
                ),
            ],
        )
        self.repo.save_conversation(conv)

        query = "The idea where I don't have to physically go upstairs to inspect something."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")


if __name__ == "__main__":
    unittest.main()
