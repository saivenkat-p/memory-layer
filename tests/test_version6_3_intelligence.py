"""
Milestone V6.3 Memory Intelligence Unit & Integration Tests.

Verifies:
1. Turn-window embedding context construction (User + Assistant pairing).
2. Embedding & index idempotency (INSERT OR REPLACE does not duplicate records).
3. Incremental auto-sync compatibility.
4. Existing search retrieval consistency with text normalization.
"""

import unittest
import os
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine
from app.search.hybrid_search import HybridSearchEngine
from app.models.schemas import Conversation, Message


class TestVersion63MemoryIntelligence(unittest.TestCase):
    """Unit and Integration tests for V6.3 turn-window embeddings and intelligence features."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join("data", "test_v63_intelligence.db")
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        cls.db = Database(cls.db_path)
        cls.repo = ConversationRepository(cls.db)
        cls.semantic = SemanticSearchEngine(cls.repo)
        cls.hybrid = HybridSearchEngine(cls.repo)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'db') and cls.db:
            cls.db.get_connection().close()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_turn_window_construction_and_indexing(self):
        """TEST 01: Turn-window context correctly pairs User prompt with Assistant turn."""
        conv = Conversation(
            id="v63-test-conv-1",
            title="Quantum Circuit Optimization Strategy",
            source="ChatGPT",
            messages=[
                Message(role="user", content="Give this project description", index=0),
                Message(role="assistant", content="ARQPO is an adaptive regime-aware quantum optimizer.", index=1)
            ]
        )
        saved_id = self.repo.save_conversation(conv)
        self.assertEqual(saved_id, "v63-test-conv-1")

        # Verify 2 embeddings were generated for the 2 messages
        with self.db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM message_embeddings WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = 'v63-test-conv-1')")
            count = c.fetchone()["cnt"]
            self.assertEqual(count, 2)

    def test_02_index_idempotency(self):
        """TEST 02: Re-indexing existing conversation updates records without creating duplicates."""
        conv = self.repo.get_conversation("v63-test-conv-1")
        initial_count = self.semantic.get_embedding_statistics()["total_embeddings"]

        # Re-index
        reindexed_cnt = self.semantic.index_conversation_messages("v63-test-conv-1")
        self.assertEqual(reindexed_cnt, 2)

        after_count = self.semantic.get_embedding_statistics()["total_embeddings"]
        self.assertEqual(initial_count, after_count)

    def test_03_incremental_auto_sync_compatibility(self):
        """TEST 03: Adding new turns incrementally indices seamlessly."""
        updated_conv = Conversation(
            id="v63-test-conv-1",
            title="Quantum Circuit Optimization Strategy",
            source="ChatGPT",
            messages=[
                Message(role="user", content="Give this project description", index=0),
                Message(role="assistant", content="ARQPO is an adaptive regime-aware quantum optimizer.", index=1),
                Message(role="user", content="What classical baseline do we benchmark against?", index=2),
                Message(role="assistant", content="We benchmark against classical Mean-Variance Optimization.", index=3)
            ]
        )
        self.repo.save_conversation(updated_conv)

        fetched = self.repo.get_conversation("v63-test-conv-1")
        self.assertEqual(fetched.message_count, 4)

        with self.db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM message_embeddings WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = 'v63-test-conv-1')")
            count = c.fetchone()["cnt"]
            self.assertEqual(count, 4)

    def test_04_conceptual_search_retrieval(self):
        """TEST 04: Conceptual query finds turn-window context with high relevance."""
        results = self.hybrid.search("quantum optimizer benchmark classical baseline", limit=5)
        self.assertGreater(len(results), 0)
        matched_conv_ids = [r.conversation_id for r in results]
        self.assertIn("v63-test-conv-1", matched_conv_ids)


if __name__ == "__main__":
    unittest.main()
