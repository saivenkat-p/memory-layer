"""
Comprehensive Test Suite for Hybrid Search Architecture.

Tests cover:
A. Exact keyword query.
B. Semantically similar query with different wording.
C. Completely unrelated query.
D. Query containing one matching keyword but otherwise unrelated context (incidental match false positive elimination).
E. Ranking multiple results by hybrid relevance.
F. No-result behavior.
"""

import unittest
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine


class TestHybridSearch(unittest.TestCase):

    def setUp(self):
        self.db = Database(":memory:")
        self.repo = ConversationRepository(self.db)
        self.hybrid_engine = HybridSearchEngine(self.repo)

        # Seed test dataset
        c1 = Conversation(
            title="Smart Water Tank IoT Monitoring Idea",
            source="ChatGPT",
            category="Startup Idea",
            tags=["IoT", "Water", "Automation"],
            description="Automatic tank level monitoring system",
            messages=[
                Message(
                    role="user",
                    content="I don't want to climb the stairs to check whether the overhead tank is full.",
                    index=0,
                ),
                Message(
                    role="assistant",
                    content="You can build a prototype with an ESP32 microcontroller, ultrasonic distance sensor, and relay module to automatically stop the motor when full.",
                    index=1,
                ),
            ],
        )

        c2 = Conversation(
            title="Quantum Computing with Qiskit",
            source="TXT",
            category="Learning",
            tags=["Quantum", "Python"],
            description="Qiskit circuit basics",
            messages=[
                Message(
                    role="user",
                    content="How do I create a QuantumCircuit in Qiskit to measure quantum superposition?",
                    index=0,
                ),
                Message(
                    role="assistant",
                    content="Use qc = QuantumCircuit(2, 2) and apply Hadamard gate qc.h(0) in Qiskit.",
                    index=1,
                ),
            ],
        )

        self.repo.save_conversation(c1)
        self.repo.save_conversation(c2)

    # Test A: Exact Keyword Query
    def test_A_exact_keyword_query(self):
        results = self.hybrid_engine.search("automatically stop motor when tank is full")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank IoT Monitoring Idea")

    # Test B: Semantically Similar Query with Different Wording
    def test_B_semantically_similar_query_different_wording(self):
        results = self.hybrid_engine.search("the idea about avoiding going upstairs to check the water")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank IoT Monitoring Idea")

    # Test C: Completely Unrelated Query
    def test_C_completely_unrelated_query(self):
        results = self.hybrid_engine.search("climbing mountain")
        self.assertEqual(len(results), 0)

    # Test D: Query containing one matching keyword but otherwise unrelated context
    def test_D_incidental_keyword_false_positive_elimination(self):
        # "prototype" exists in water tank conversation, but "climbing mountain prototype" is semantically unrelated!
        results = self.hybrid_engine.search("climbing mountain prototype")
        
        # Verify water tank is NOT returned as a valid match (or score is negligible)
        matching_titles = [r.conversation_title for r in results if r.score > 25]
        self.assertNotIn("Smart Water Tank IoT Monitoring Idea", matching_titles)

    # Test E: Ranking Multiple Results
    def test_E_ranking_multiple_results(self):
        results = self.hybrid_engine.search("quantum superposition circuit")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Quantum Computing with Qiskit")

    # Test F: No-Result Behavior
    def test_F_no_result_behavior(self):
        results = self.hybrid_engine.search("completely random non-existent query 12345")
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
