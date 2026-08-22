"""
Unit test suite for SearchEngine and AskMyMemoryAssistant.
"""

import unittest
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchEngine
from app.search.hybrid_search import HybridSearchEngine
from app.ai.memory_assistant import AskMyMemoryAssistant


class TestSearchAndAI(unittest.TestCase):

    def setUp(self):
        self.db = Database(":memory:")
        self.repo = ConversationRepository(self.db)
        self.search_engine = SearchEngine(self.repo)
        self.assistant = AskMyMemoryAssistant(HybridSearchEngine(self.repo))

        # Seed test data
        c1 = Conversation(
            title="Smart Water Tank IoT Monitoring Idea",
            source="ChatGPT",
            category="Startup Idea",
            tags=["IoT", "Water"],
            description="Automatic tank level monitoring system",
            messages=[
                Message(role="user", content="I want to build an automated water tank motor monitor.", index=0),
                Message(role="assistant", content="You can use ESP32 microcontrollers with ultrasonic sensors.", index=1),
                Message(role="user", content="What components do I need?", index=2),
                Message(role="assistant", content="ESP32, Relay Module, and Ultrasonic Sensor.", index=3),
            ]
        )

        c2 = Conversation(
            title="Quantum Computing with Qiskit",
            source="TXT",
            category="Learning",
            tags=["Quantum", "Python"],
            description="Qiskit circuit basics",
            messages=[
                Message(role="user", content="How do I create a QuantumCircuit in Qiskit?", index=0),
                Message(role="assistant", content="Use qc = QuantumCircuit(2, 2) in Qiskit.", index=1),
            ]
        )

        self.repo.save_conversation(c1)
        self.repo.save_conversation(c2)

    def test_keyword_search_match(self):
        results = self.search_engine.search("water tank")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank IoT Monitoring Idea")
        self.assertIn("water tank", results[0].matched_content.lower())

    def test_keyword_search_qiskit(self):
        results = self.search_engine.search("Qiskit")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].conversation_title, "Quantum Computing with Qiskit")

    def test_source_context_retrieval(self):
        convs = self.repo.list_conversations()
        c1_id = [c.id for c in convs if "Water" in c.title][0]

        context = self.search_engine.get_source_context(c1_id, target_index=1, window=1)
        self.assertIsNotNone(context["target_message"])
        self.assertEqual(context["target_message"].index, 1)
        self.assertEqual(len(context["previous_messages"]), 1)
        self.assertEqual(context["previous_messages"][0].index, 0)
        self.assertEqual(len(context["following_messages"]), 1)
        self.assertEqual(context["following_messages"][0].index, 2)

    def test_ask_my_memory_success(self):
        answer = self.assistant.ask("What startup ideas did I discuss?")
        self.assertTrue(answer.found)
        self.assertTrue("Startup" in answer.summary or "Water" in answer.summary)
        self.assertGreater(len(answer.sources), 0)

    def test_ask_my_memory_no_results(self):
        answer = self.assistant.ask("Where did I discuss government certificates?")
        self.assertFalse(answer.found)
        self.assertIn("No sufficiently relevant memory found", answer.summary)


if __name__ == "__main__":
    unittest.main()
