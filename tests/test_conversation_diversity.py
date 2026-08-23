"""
Milestone V6.4-B Experiment 2: Conversation Diversity & Flooding Control Tests.

Verifies:
1. Flooding Suppression: Single verbose conversations with dozens of low-value matches do not crowd out distinct relevant conversations.
2. High-Value Secondary Match Preservation: Genuinely strong secondary messages from the same conversation are preserved when their adjusted score exceeds other candidates.
3. In-Conversation Search Exemption: FindHereEngine operates exclusively on the target conversation without cross-conversation diversity decay.
4. Configurable Diversity Parameter: Passing diversity_decay=1.0 disables decay and returns raw score order.
5. Context Expansion Post-Diversity: Diversified results receive multi-turn contextual enrichment cleanly.
"""

import unittest
import os
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.search.find_here import FindHereEngine


class TestConversationDiversity(unittest.TestCase):
    """Test suite for V6.4-B Experiment 2 Conversation Diversity & Flooding Control."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join("data", "test_v64b_diversity.db")
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

        cls.db = Database(cls.db_path)
        cls.repo = ConversationRepository(cls.db)
        cls.hybrid_engine = HybridSearchEngine(cls.repo)
        cls.find_here_engine = FindHereEngine(cls.repo)

        # 1. Verbose Conversation A (10 messages mentioning 'optimization' and 'pipeline')
        msgs_a = []
        for i in range(10):
            msgs_a.append(
                Message(
                    id=f"msg-a-{i}",
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Step {i}: We discuss neural architecture optimization and pipeline step {i}.",
                    index=i,
                )
            )
        cls.conv_a = Conversation(
            id="conv-verbose-a",
            title="Verbose Architecture Pipeline Discussion",
            source="ChatGPT",
            messages=msgs_a,
        )

        # 2. Concise Conversation B (2 messages, distinct discussion on optimization benchmarks)
        cls.conv_b = Conversation(
            id="conv-concise-b",
            title="Benchmark Comparison for Optimization",
            source="Gemini",
            messages=[
                Message(
                    id="msg-b-0",
                    role="user",
                    content="What is the final benchmark optimization speedup across hardware backends?",
                    index=0,
                ),
                Message(
                    id="msg-b-1",
                    role="assistant",
                    content="The benchmark optimization achieves a 3.4x speedup.",
                    index=1,
                ),
            ],
        )

        # 3. Third Distinct Conversation C
        cls.conv_c = Conversation(
            id="conv-distinct-c",
            title="Autonomous Agent Memory Persistence",
            source="Claude",
            messages=[
                Message(
                    id="msg-c-0",
                    role="user",
                    content="How does memory persistence optimize autonomous agent decision loops?",
                    index=0,
                )
            ],
        )

        cls.repo.save_conversation(cls.conv_a)
        cls.repo.save_conversation(cls.conv_b)
        cls.repo.save_conversation(cls.conv_c)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db") and cls.db:
            cls.db.get_connection().close()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_flooding_suppression_promotes_distinct_conversations(self):
        """TEST 01: Verbose conversation with 10 messages does not monopolize all top 5 result slots."""
        results = self.hybrid_engine.search("optimization", limit=5, diversity_decay=0.85)
        self.assertGreater(len(results), 1)

        conv_ids = [r.conversation_id for r in results]
        unique_convs = set(conv_ids)

        # Must contain at least 2 distinct conversations in the Top 5
        self.assertGreater(len(unique_convs), 1, "Diversity decay must ensure multiple conversations appear in Top-5")
        self.assertIn("conv-concise-b", conv_ids, "Conversation B must not be buried under 10 messages from Conversation A")

    def test_02_high_value_secondary_message_preserved(self):
        """TEST 02: A strong second message from the same conversation can still appear if relevant."""
        results = self.hybrid_engine.search("optimization", limit=5, diversity_decay=0.85)
        conv_a_results = [r for r in results if r.conversation_id == "conv-verbose-a"]
        # Conv A should have multiple messages in Top 5 (e.g. 2 or 3), demonstrating that strong secondary hits are preserved
        self.assertGreaterEqual(len(conv_a_results), 2, "Strong secondary messages from same conversation must be preserved")
        # But should not take all 5 slots when Conv B also matches
        self.assertLessEqual(len(conv_a_results), 4, "Single conversation must not take all slots when distinct matches exist")

    def test_03_in_conversation_search_exempt_from_decay(self):
        """TEST 03: FindHereEngine searches within a single conversation and is not penalized by diversity decay."""
        results = self.find_here_engine.search_in_conversation("conv-verbose-a", "optimization", limit=10)
        # All returned messages belong to conv-verbose-a without cross-conversation decay
        self.assertGreater(len(results), 3)
        for r in results:
            self.assertEqual(r.conversation_id, "conv-verbose-a")

    def test_04_disable_diversity_decay_flag(self):
        """TEST 04: Setting diversity_decay=1.0 yields raw hybrid ranking order."""
        raw_results = self.hybrid_engine.search("optimization", limit=5, diversity_decay=1.0)
        # With decay=1.0, Conv A with 10 hits can dominate top slots
        conv_a_count = sum(1 for r in raw_results if r.conversation_id == "conv-verbose-a")
        self.assertGreaterEqual(conv_a_count, 3)

    def test_05_context_expansion_works_post_diversity(self):
        """TEST 05: Results selected after diversity decay are properly enriched with multi-turn context."""
        results = self.hybrid_engine.search("optimization benchmark", limit=3, expand_context=True)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertTrue(hasattr(top, "context_messages"))
        self.assertTrue(hasattr(top, "context_text"))
        self.assertGreater(len(top.context_text), 0, "Top diversified result must have non-empty context_text")


if __name__ == "__main__":
    unittest.main()
