"""
Milestone V6.4-B Experiment 1: Lexical Length Bias & Term Frequency Saturation Tests.

Verifies:
1. Single occurrence: Short messages receive high term density scoring.
2. Repeated occurrence: Scores saturate sublinearly and do NOT scale unbounded with message size.
3. Short vs Huge document comparison: A concise message with high term density outranks a huge document with scattered term repetitions.
4. Exact keyword searches (e.g., 'Qiskit', 'water tank') continue to function correctly.
5. Semantic-only fallback: Zero-vocabulary overlap queries remain 100% functional via V6.4-A adaptive semantic fallback.
"""

import unittest
import os
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchEngine
from app.search.hybrid_search import HybridSearchEngine


class TestLexicalSaturation(unittest.TestCase):
    """Test suite for V6.4-B Experiment 1 BM25 term-frequency saturation and length normalization."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join("data", "test_v64b_saturation.db")
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

        cls.db = Database(cls.db_path)
        cls.repo = ConversationRepository(cls.db)
        cls.search_engine = SearchEngine(cls.repo)
        cls.hybrid_engine = HybridSearchEngine(cls.repo)

        # 1. Concise Target Conversation: 30 words, 1 occurrence of 'regime' and 'clustering'
        cls.conv_short = Conversation(
            id="test-conv-short-regime",
            title="Market Regime Discussion",
            source="ChatGPT",
            messages=[
                Message(
                    id="msg-short-1",
                    role="user",
                    content="We analyze financial market regime shifts using Gaussian mixture clustering on volatility series.",
                    index=0,
                )
            ],
        )

        # 2. Huge Document Dump Conversation: 800 words, 8 scattered occurrences of 'regime' and 'clustering'
        filler = "The system executes portfolio allocation based on classical benchmark optimization and backtesting metrics. " * 35
        huge_content = (
            f"Introduction to asset management: {filler} "
            f"Here we mention market regime and clustering. {filler} "
            f"Another reference to market regime and clustering in section 4. {filler} "
            f"Further discussion of market regime and clustering for investors. {filler} "
            f"Conclusion on market regime clustering."
        )
        cls.conv_huge = Conversation(
            id="test-conv-huge-doc",
            title="Comprehensive Portfolio Allocation Whitepaper",
            source="ChatGPT",
            messages=[
                Message(
                    id="msg-huge-1",
                    role="assistant",
                    content=huge_content,
                    index=0,
                )
            ],
        )

        # 3. Exact Keyword Conversation
        cls.conv_exact = Conversation(
            id="test-conv-exact-qiskit",
            title="Quantum Computing with Qiskit",
            source="TXT",
            messages=[
                Message(
                    id="msg-exact-1",
                    role="user",
                    content="How do I create a QuantumCircuit in Qiskit to measure entanglement?",
                    index=0,
                ),
                Message(
                    id="msg-exact-2",
                    role="assistant",
                    content="Use qc = QuantumCircuit(2, 2) in Qiskit.",
                    index=1,
                ),
            ],
        )

        # 4. Pure Semantic Conversation (Zero Vocabulary Overlap with "physically inspect overhead supply")
        cls.conv_semantic = Conversation(
            id="test-conv-semantic-tank",
            title="Smart Water Tank IoT Monitoring",
            source="ChatGPT",
            messages=[
                Message(
                    id="msg-sem-1",
                    role="user",
                    content="I don't want to climb the stairs to check whether the overhead tank is full. I want automatic motor shutoff.",
                    index=0,
                )
            ],
        )

        cls.repo.save_conversation(cls.conv_short)
        cls.repo.save_conversation(cls.conv_huge)
        cls.repo.save_conversation(cls.conv_exact)
        cls.repo.save_conversation(cls.conv_semantic)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db") and cls.db:
            cls.db.get_connection().close()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_single_occurrence_meaningful_score(self):
        """TEST 01: A concise message containing the query term once receives a strong density score."""
        results = self.search_engine.search("regime clustering")
        short_res = [r for r in results if r.conversation_id == "test-conv-short-regime"]
        self.assertEqual(len(short_res), 1)
        self.assertGreater(short_res[0].score, 1.0, "Short message should achieve high BM25 term density score")

    def test_02_repeated_occurrence_saturates_sublinearly(self):
        """TEST 02: A huge document with 8 term repetitions does NOT receive 8x the score (saturates)."""
        results = self.search_engine.search("regime clustering")
        short_res = [r for r in results if r.conversation_id == "test-conv-short-regime"][0]
        huge_res = [r for r in results if r.conversation_id == "test-conv-huge-doc"][0]

        # The huge message has 8x the term counts, but its BM25 score must not be 8x higher
        ratio = huge_res.score / short_res.score
        self.assertLess(ratio, 2.0, "BM25 saturation and length normalization must cap score ratio far below raw 8x occurrence count")

    def test_03_short_concise_message_outranks_huge_document(self):
        """TEST 03: Concise message with high keyword density outranks the huge diluted document in Hybrid Search."""
        results = self.hybrid_engine.search("market regime clustering", limit=5)
        self.assertGreater(len(results), 0)
        # The concise dedicated conversation should be Rank #1
        self.assertEqual(results[0].conversation_id, "test-conv-short-regime", "Concise message must outrank diluted document dump")

    def test_04_exact_keyword_search_remains_functional(self):
        """TEST 04: Exact keyword queries like 'Qiskit' continue to retrieve expected matches."""
        results = self.hybrid_engine.search("Qiskit QuantumCircuit", limit=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_id, "test-conv-exact-qiskit")

    def test_05_semantic_only_fallback_remains_functional(self):
        """TEST 05: Zero-vocabulary-overlap semantic query retrieves target conversation via V6.4-A fallback."""
        query = "A way to remotely know whether a household resource has enough supply"
        results = self.hybrid_engine.search(query, limit=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_id, "test-conv-semantic-tank")


if __name__ == "__main__":
    unittest.main()
