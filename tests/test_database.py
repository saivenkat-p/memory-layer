"""
Unit test suite for Database and ConversationRepository using an in-memory SQLite database.
"""

import unittest
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository


class TestDatabaseRepository(unittest.TestCase):

    def setUp(self):
        # Use in-memory SQLite database for fast, isolated tests
        self.db = Database(":memory:")
        self.repo = ConversationRepository(self.db)

    def test_save_and_get_conversation(self):
        msg1 = Message(role="user", content="How do I monitor water level?", index=0)
        msg2 = Message(role="assistant", content="Use an ultrasonic sensor and relay.", index=1)
        conv = Conversation(
            title="Water Monitoring",
            source="ChatGPT",
            messages=[msg1, msg2],
            category="Startup Idea",
            tags=["IoT", "Water"],
            description="Smart water tank project",
        )

        conv_id = self.repo.save_conversation(conv)
        self.assertEqual(conv_id, conv.id)

        retrieved = self.repo.get_conversation(conv_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Water Monitoring")
        self.assertEqual(retrieved.source, "ChatGPT")
        self.assertEqual(retrieved.category, "Startup Idea")
        self.assertEqual(retrieved.tags, ["IoT", "Water"])
        self.assertEqual(retrieved.message_count, 2)
        self.assertEqual(retrieved.messages[0].content, "How do I monitor water level?")
        self.assertEqual(retrieved.messages[1].content, "Use an ultrasonic sensor and relay.")

    def test_list_conversations(self):
        conv1 = Conversation(title="Conv 1", messages=[Message(role="user", content="Hi", index=0)])
        conv2 = Conversation(title="Conv 2", messages=[Message(role="user", content="Hello", index=0)])

        self.repo.save_conversation(conv1)
        self.repo.save_conversation(conv2)

        convs = self.repo.list_conversations()
        self.assertEqual(len(convs), 2)

    def test_update_metadata(self):
        conv = Conversation(
            title="Metadata Test",
            messages=[Message(role="user", content="Test", index=0)],
        )
        self.repo.save_conversation(conv)

        updated = self.repo.update_metadata(
            conv.id,
            category="Research",
            tags=["AI", "Quantum"],
            description="New description",
        )
        self.assertTrue(updated)

        retrieved = self.repo.get_conversation(conv.id)
        self.assertEqual(retrieved.category, "Research")
        self.assertEqual(retrieved.tags, ["AI", "Quantum"])
        self.assertEqual(retrieved.description, "New description")

    def test_delete_conversation(self):
        conv = Conversation(
            title="Delete Test",
            messages=[Message(role="user", content="To be deleted", index=0)],
        )
        self.repo.save_conversation(conv)

        # Ensure conversation and messages exist
        self.assertIsNotNone(self.repo.get_conversation(conv.id))

        # Delete conversation
        deleted = self.repo.delete_conversation(conv.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_conversation(conv.id))

        # Verify messages table is empty due to CASCADE delete
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?", (conv.id,))
            self.assertEqual(cursor.fetchone()["count"], 0)

    def test_get_stats(self):
        conv1 = Conversation(title="C1", source="ChatGPT", messages=[Message(role="user", content="M1", index=0)])
        conv2 = Conversation(title="C2", source="TXT", messages=[Message(role="user", content="M2", index=0), Message(role="assistant", content="M3", index=1)])

        self.repo.save_conversation(conv1)
        self.repo.save_conversation(conv2)

        stats = self.repo.get_stats()
        self.assertEqual(stats["total_conversations"], 2)
        self.assertEqual(stats["total_messages"], 3)
        self.assertEqual(stats["sources"]["ChatGPT"], 1)
        self.assertEqual(stats["sources"]["TXT"], 1)


if __name__ == "__main__":
    unittest.main()
