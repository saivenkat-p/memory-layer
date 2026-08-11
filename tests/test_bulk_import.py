"""
Unit tests for Bulk History Import System, Duplicate Prevention, ZIP Archives, and Progress Tracking.
"""

import io
import os
import zipfile
import unittest

from app.models.schemas import Conversation, Message
from app.parsers.json_parser import JSONParser
from app.parsers.bulk_parser import BulkParser
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.services.bulk_import import BulkImportEngine
from app.search.hybrid_search import HybridSearchEngine


class TestBulkImportSystem(unittest.TestCase):
    """Acceptance tests for Milestone 8 Bulk History Import capabilities."""

    def setUp(self):
        self.test_db_path = f"test_bulk_mem_{os.getpid()}.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.db = Database(self.test_db_path)
        self.repo = ConversationRepository(self.db)
        self.engine = BulkImportEngine(self.repo)

    def tearDown(self):
        if hasattr(self.db, "_memory_conn") and self.db._memory_conn:
            try:
                self.db._memory_conn.close()
            except Exception:
                pass
        del self.repo
        del self.engine
        del self.db
        import gc
        gc.collect()
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_01_parse_chatgpt_bulk_conversations_json(self):
        """Tests parsing a ChatGPT bulk export conversations.json list structure."""
        bulk_json_data = [
            {
                "title": "Smart Solar Panel Tracker",
                "create_time": 1700000000,
                "mapping": {
                    "node_1": {
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["I want to build a solar panel tracking system."]},
                            "create_time": 1700000001
                        }
                    },
                    "node_2": {
                        "message": {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["You can use light dependent resistors (LDRs) and servo motors."]},
                            "create_time": 1700000002
                        }
                    }
                }
            },
            {
                "title": "Cricket Equipment Rental App",
                "create_time": 1700000100,
                "mapping": {
                    "node_10": {
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["How to start a cricket gear rental business?"]},
                            "create_time": 1700000101
                        }
                    }
                }
            }
        ]

        parser = JSONParser()
        json_bytes = io.BytesIO()
        import json
        json_bytes.write(json.dumps(bulk_json_data).encode("utf-8"))

        convs = parser.parse_bulk(json_bytes.getvalue(), filename="conversations.json")
        self.assertEqual(len(convs), 2)
        self.assertEqual(convs[0].title, "Smart Solar Panel Tracker")
        self.assertEqual(convs[0].source, "ChatGPT")
        self.assertEqual(convs[1].title, "Cricket Equipment Rental App")

    def test_02_parse_zip_archive(self):
        """Tests extracting and parsing multiple files from a ZIP archive."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("chat1.txt", "User: I need a python script for scraping\nBot: You can use BeautifulSoup")
            zf.writestr(
                "chat2.json",
                '{"title": "Qiskit Quantum Notes", "messages": [{"role": "user", "content": "What is Qiskit?"}]}'
            )

        bulk_parser = BulkParser()
        convs = bulk_parser.parse_archive_or_file(zip_buffer.getvalue(), filename="history_export.zip")
        self.assertEqual(len(convs), 2)

        titles = [c.title for c in convs]
        self.assertIn("Chat1", titles)
        self.assertIn("Qiskit Quantum Notes", titles)

    def test_03_bulk_import_engine_progress_and_duplicates(self):
        """Tests BulkImportEngine progress reporting and duplicate conversation skipping."""
        conv1 = Conversation(
            title="Automated Irrigation System",
            source="ChatGPT",
            messages=[Message(role="user", content="I need to automate soil moisture watering.", index=0)]
        )
        conv2 = Conversation(
            title="AI Recipe Assistant",
            source="Gemini",
            messages=[Message(role="user", content="Suggest a dinner recipe with spinach.", index=0)]
        )

        # 1. First Import
        import_progress = []

        def tracking_cb(curr, tot, msg):
            import_progress.append((curr, tot, msg))

        # Save conv1 & conv2 using bulk engine directly
        import json
        bulk_data = [
            {"title": conv1.title, "messages": [{"role": "user", "content": conv1.messages[0].content}]},
            {"title": conv2.title, "messages": [{"role": "user", "content": conv2.messages[0].content}]},
        ]
        json_bytes = json.dumps(bulk_data).encode("utf-8")

        res1 = self.engine.import_archive_or_file(json_bytes, "history.json", progress_callback=tracking_cb)
        self.assertEqual(res1.conversations_detected, 2)
        self.assertEqual(res1.conversations_imported, 2)
        self.assertEqual(res1.duplicates_skipped, 0)
        self.assertEqual(res1.messages_imported, 2)

        # Verify progress callback was invoked
        self.assertTrue(len(import_progress) > 0)

        # 2. Re-import Same Dataset (Duplicate Detection)
        res2 = self.engine.import_archive_or_file(json_bytes, "history.json", skip_duplicates=True)
        self.assertEqual(res2.conversations_detected, 2)
        self.assertEqual(res2.conversations_imported, 0)
        self.assertEqual(res2.duplicates_skipped, 2)

    def test_04_search_across_bulk_imported_corpus(self):
        """Tests running hybrid search across a bulk imported collection of conversations."""
        conv1 = Conversation(
            title="Smart Water Tank IoT Monitoring Idea",
            source="ChatGPT",
            messages=[
                Message(role="user", content="I don't want to climb the stairs to check overhead tank water level.", index=0),
                Message(role="assistant", content="You can use an ultrasonic sensor HC-SR04 to remotely measure water level.", index=1),
            ]
        )
        conv2 = Conversation(
            title="Government Service Digital Portal",
            source="Claude",
            messages=[
                Message(role="user", content="How to build a single sign-on portal for citizen utility applications?", index=0),
            ]
        )

        self.repo.save_conversation(conv1)
        self.repo.save_conversation(conv2)

        hybrid_search = HybridSearchEngine(self.repo)
        results = hybrid_search.search("A system to remotely measure overhead tank without going upstairs")

        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank IoT Monitoring Idea")


if __name__ == "__main__":
    unittest.main()
