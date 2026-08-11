"""
Unit and Integration Tests for Version 3 Features:
1. 🔍 FIND HERE (In-Conversation Temporary Search & Non-Pollution Guarantee)
2. 🌿 CONTINUE (Topic Extraction, Chronological Order, & Parent-Child Relationships)
"""

import os
import unittest

from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.find_here import FindHereEngine
from app.services.topic_extractor import TopicExtractionEngine


class TestVersion3Features(unittest.TestCase):
    """Test suite covering Version 3 Find Here and Continue Topic capabilities."""

    def setUp(self):
        self.test_db_path = f"test_v3_{os.getpid()}.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

        self.db = Database(self.test_db_path)
        self.repo = ConversationRepository(self.db)
        self.find_here = FindHereEngine(self.repo)
        self.topic_extractor = TopicExtractionEngine(self.repo)

    def tearDown(self):
        if hasattr(self.db, "_memory_conn") and self.db._memory_conn:
            try:
                self.db._memory_conn.close()
            except Exception:
                pass
        del self.repo
        del self.find_here
        del self.topic_extractor
        del self.db
        import gc
        gc.collect()

        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_01_temporary_find_here_non_pollution(self):
        """
        TEST 1: Find Here searches strictly inside conversation and does NOT pollute DB.
        """
        conv = Conversation(
            title="Multi Topic Discussion",
            source="ChatGPT",
            messages=[
                Message(role="user", content="Let's discuss quantum computing.", index=0),
                Message(role="assistant", content="Qiskit can represent quantum circuits and gates.", index=1),
                Message(role="user", content="Let's switch to the water tank project.", index=2),
            ]
        )
        conv_id = self.repo.save_conversation(conv)

        # Count DB messages before find search
        stats_before = self.repo.get_stats()

        # Execute Find Here search
        results = self.find_here.search_in_conversation(conv_id, "quantum circuits")

        # Count DB messages after find search
        stats_after = self.repo.get_stats()

        # 1. Assert correct match returned
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].msg_index, 1)

        # 2. Assert strict non-pollution: message count remains exactly 3
        self.assertEqual(stats_before["total_messages"], stats_after["total_messages"])

    def test_02_current_conversation_isolation(self):
        """
        TEST 2: Searching inside Conversation A does NOT return results from Conversation B.
        """
        conv_a = Conversation(
            title="Quantum Discussion",
            source="ChatGPT",
            messages=[Message(role="user", content="Qiskit state vector simulator.", index=0)]
        )
        conv_b = Conversation(
            title="Water Tank Discussion",
            source="ChatGPT",
            messages=[Message(role="user", content="Ultrasonic sensor for overhead water tank level.", index=0)]
        )

        id_a = self.repo.save_conversation(conv_a)
        id_b = self.repo.save_conversation(conv_b)

        # Search inside Conversation A for 'water tank'
        results = self.find_here.search_in_conversation(id_a, "water tank")

        # Must return ZERO results from Conversation B
        for r in results:
            self.assertEqual(r.conversation_id, id_a)

    def test_03_paraphrased_find_here(self):
        """
        TEST 3: Find Here matches paraphrased natural language without exact keywords.
        """
        conv = Conversation(
            title="Home Automation Ideas",
            source="ChatGPT",
            messages=[
                Message(
                    role="user",
                    content="I want the pump to automatically stop once the overhead tank reaches full capacity.",
                    index=0
                )
            ]
        )
        conv_id = self.repo.save_conversation(conv)

        results = self.find_here.search_in_conversation(conv_id, "automatically turn off the water motor")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].msg_index, 0)

    def test_04_topic_extraction(self):
        """
        TEST 4: Topic extraction selects Memory Layer messages and excludes unrelated quantum/college topics.
        """
        conv = Conversation(
            title="Huge Mixed Conversation",
            source="ChatGPT",
            messages=[
                Message(role="user", content="What were my college exam scores?", index=0),
                Message(role="user", content="How to build Qiskit quantum circuits?", index=1),
                Message(role="user", content="I want to create a Personal AI Memory Layer to search old chats.", index=2),
                Message(role="assistant", content="A Personal AI Memory Layer ingests exports and indexes vectors locally.", index=3),
                Message(role="user", content="What startup ideas do I have for cricket rentals?", index=4),
            ]
        )
        conv_id = self.repo.save_conversation(conv)

        preview = self.topic_extractor.extract_topic_context(conv_id, "Personal AI Memory Layer")

        # Selected indices should include indices 2 & 3
        extracted_indices = [m.original_index for m in preview.selected_messages]
        self.assertIn(2, extracted_indices)
        self.assertIn(3, extracted_indices)
        self.assertNotIn(0, extracted_indices)

    def test_05_chronological_order(self):
        """
        TEST 5: Extracted topic context maintains strict chronological sequence (e.g. 80 -> 84 -> 91).
        """
        conv = Conversation(
            title="Long Discussion",
            source="ChatGPT",
            messages=[
                Message(role="user", content="Unrelated topic A", index=0),
                Message(role="user", content="Memory Layer idea proposal", index=1),
                Message(role="user", content="Unrelated topic B", index=2),
                Message(role="user", content="Memory Layer local embeddings architecture", index=3),
            ]
        )
        conv_id = self.repo.save_conversation(conv)

        preview = self.topic_extractor.extract_topic_context(conv_id, "Memory Layer architecture")
        indices = [m.original_index for m in preview.selected_messages]

        # Verify sorted chronological sequence
        self.assertEqual(indices, sorted(indices))

    def test_06_parent_child_relationship_and_provenance(self):
        """
        TEST 6: Continuation creates new focused chat, links relationship, and retains provenance references.
        """
        parent_conv = Conversation(
            title="All Ideas Collection",
            source="ChatGPT",
            messages=[
                Message(role="user", content="Water tank monitoring sensor idea", index=0),
                Message(role="assistant", content="Use ultrasonic sensor HC-SR04 with ESP32", index=1),
            ]
        )
        parent_id = self.repo.save_conversation(parent_conv)

        # Extract & create focused child conversation
        preview = self.topic_extractor.extract_topic_context(parent_id, "Water tank monitoring")
        msg_ids = [m.message_id for m in preview.selected_messages]

        child_conv = self.topic_extractor.create_continued_conversation(parent_id, "Water tank monitoring", msg_ids)

        # 1. Verify child title and messages
        self.assertTrue(child_conv.title.startswith("Continued:"))
        self.assertEqual(child_conv.message_count, len(msg_ids))

        # 2. Verify message provenance attributes
        for m in child_conv.messages:
            self.assertEqual(m.source_conversation_id, parent_id)
            self.assertIsNotNone(m.source_message_id)

        # 3. Verify relationship record in SQLite DB
        rel_data = self.repo.get_relationships(child_conv.id)
        self.assertIsNotNone(rel_data["parent"])
        self.assertEqual(rel_data["parent"]["parent_id"], parent_id)
        self.assertEqual(rel_data["parent"]["topic"], "Water tank monitoring")


if __name__ == "__main__":
    unittest.main()
