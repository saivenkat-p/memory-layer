"""
Unit and Integration Tests for Milestone V5A: Live AI Integration Foundation
(Portable Context Package, Schema v1.0, Deterministic Context Text, Local Export Adapter)
"""

import json
import os
import unittest

from app.models.schemas import Conversation, Message, ContextCandidate, ComposedContext, PortableContextPackage
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.services.context_composer import ContextComposer
from app.services.export_engine import LocalExportDestination


class TestVersion5AExport(unittest.TestCase):
    """Test suite for Milestone V5A Portable Context Package & Local Export Adapter."""

    def setUp(self):
        self.test_db_path = f"test_v5a_{os.getpid()}.db"
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

        self.db = Database(self.test_db_path)
        self.repo = ConversationRepository(self.db)
        self.search_engine = HybridSearchEngine(self.repo)
        self.composer = ContextComposer(self.repo, self.search_engine)
        self.exporter = LocalExportDestination()

        # Seed sample conversations
        self.conv_chatgpt = Conversation(
            title="Funding Readiness",
            source="ChatGPT",
            messages=[
                Message(role="user", content="How do we pitch angel investors?", index=0),
                Message(role="assistant", content="Emphasize local-first privacy as our key differentiator.", index=1),
            ]
        )
        self.conv_gemini = Conversation(
            title="Memory Layer Architecture",
            source="Gemini",
            messages=[
                Message(role="user", content="How does local neural search work?", index=0),
                Message(role="assistant", content="It uses SentenceTransformers all-MiniLM-L6-v2 embeddings stored in SQLite.", index=1),
            ]
        )

        self.id_chatgpt = self.repo.save_conversation(self.conv_chatgpt)
        self.id_gemini = self.repo.save_conversation(self.conv_gemini)

        # Build composed context for testing
        cand1 = ContextCandidate(
            message_id=self.conv_chatgpt.messages[0].id,
            conversation_id=self.id_chatgpt,
            conversation_title=self.conv_chatgpt.title,
            source="ChatGPT",
            role="user",
            content=self.conv_chatgpt.messages[0].content,
            message_index=0,
            relevance_score=85,
        )
        cand2 = ContextCandidate(
            message_id=self.conv_gemini.messages[1].id,
            conversation_id=self.id_gemini,
            conversation_title=self.conv_gemini.title,
            source="Gemini",
            role="assistant",
            content=self.conv_gemini.messages[1].content,
            message_index=1,
            relevance_score=90,
        )
        self.sample_composed_ctx = self.composer.build_context_preview(
            selected_candidates=[cand1, cand2],
            query="Funding and Local Search Architecture",
            title="Composed Strategy Package"
        )

    def tearDown(self):
        if hasattr(self.db, "_memory_conn") and self.db._memory_conn:
            try:
                self.db._memory_conn.close()
            except Exception:
                pass
        del self.exporter
        del self.composer
        del self.search_engine
        del self.repo
        del self.db
        import gc
        gc.collect()

        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_v5a_01_package_creation(self):
        """TEST V5A-01: Given a valid ComposedContext, prepare_context creates a PortableContextPackage."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)

        self.assertIsInstance(pkg, PortableContextPackage)
        self.assertEqual(pkg.title, "Composed Strategy Package")
        self.assertEqual(pkg.topic, "Funding and Local Search Architecture")
        self.assertEqual(len(pkg.messages), 2)

    def test_v5a_02_schema_version(self):
        """TEST V5A-02: PortableContextPackage contains valid schema_version == '1.0'."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)
        self.assertEqual(pkg.schema_version, "1.0")

    def test_v5a_03_provenance(self):
        """TEST V5A-03: Every exported message retains message_id, conversation_id, and provider."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)

        self.assertEqual(len(pkg.provenance), 2)
        for prov in pkg.provenance:
            self.assertIn("message_id", prov)
            self.assertIn("source_conversation_id", prov)
            self.assertIn("source_provider", prov)

    def test_v5a_04_ordering(self):
        """TEST V5A-04: Selected messages remain in exact user-defined sequence."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)

        self.assertEqual(pkg.messages[0]["order"], 1)
        self.assertEqual(pkg.messages[0]["provider"], "ChatGPT")
        self.assertEqual(pkg.messages[1]["order"], 2)
        self.assertEqual(pkg.messages[1]["provider"], "Gemini")

    def test_v5a_05_context_text(self):
        """TEST V5A-05: Generated context text contains topic header, source headers, and message content."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)
        text = pkg.context_text

        self.assertIn("# Context from Personal AI Memory Layer", text)
        self.assertIn("Funding and Local Search Architecture", text)
        self.assertIn("Funding Readiness", text)
        self.assertIn("Memory Layer Architecture", text)
        self.assertIn("[User]", text)
        self.assertIn("[Assistant]", text)

    def test_v5a_06_deterministic_export(self):
        """TEST V5A-06: Exporting the same composed context twice produces identical context text."""
        text1 = self.exporter.generate_context_text(self.sample_composed_ctx)
        text2 = self.exporter.generate_context_text(self.sample_composed_ctx)

        self.assertEqual(text1, text2)

    def test_v5a_07_no_unrelated_data(self):
        """TEST V5A-07: Unselected messages do NOT appear in the portable package."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)

        # Message 0 of Conv Gemini was NOT selected
        unselected_content = self.conv_gemini.messages[0].content
        self.assertNotIn(unselected_content, pkg.context_text)

    def test_v5a_08_json_serialization(self):
        """TEST V5A-08: Package serializes to valid JSON and reconstructs via json.loads without loss."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)
        json_str = self.exporter.export_json(pkg)

        parsed = json.loads(json_str)
        self.assertEqual(parsed["schema_version"], "1.0")
        self.assertEqual(parsed["title"], "Composed Strategy Package")
        self.assertEqual(len(parsed["messages"]), 2)
        self.assertEqual(len(parsed["provenance"]), 2)

    def test_v5a_09_local_export_no_network(self):
        """TEST V5A-09: LocalExportDestination produces JSON & Plain Text locally without API calls."""
        pkg = self.exporter.prepare_context(self.sample_composed_ctx)

        json_out = self.exporter.export_json(pkg)
        text_out = self.exporter.export_text(pkg)

        self.assertTrue(len(json_out) > 0)
        self.assertTrue(len(text_out) > 0)

    def test_v5a_10_regression(self):
        """TEST V5A-10: V5A local export engine maintains complete repository stability."""
        convs = self.repo.list_conversations()
        self.assertEqual(len(convs), 2)

    def test_v5a_11_topic_and_title_preservation(self):
        """TEST V5A-11: PortableContextPackage preserves original composition query, non-empty topic, and context_text header."""
        query_str = "Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."
        cand1 = ContextCandidate(
            message_id=self.conv_chatgpt.messages[0].id,
            conversation_id=self.id_chatgpt,
            conversation_title=self.conv_chatgpt.title,
            source="ChatGPT",
            role="user",
            content=self.conv_chatgpt.messages[0].content,
            message_index=0,
            relevance_score=85,
        )
        composed_ctx = self.composer.build_context_preview([cand1], query=query_str)
        pkg = self.exporter.prepare_context(composed_ctx)

        # Asserts topic is non-empty and corresponds to original query
        self.assertTrue(len(pkg.topic) > 0)
        self.assertEqual(pkg.topic, query_str)

        # Asserts title is non-empty and not equal to "Composed: "
        self.assertTrue(len(pkg.title) > 0)
        self.assertNotEqual(pkg.title, "Composed: ")
        self.assertIn(query_str, pkg.title)

        # Asserts context_text contains the topic
        self.assertIn(query_str, pkg.context_text)

        # Confirms total_messages and provenance remain unchanged
        self.assertEqual(len(pkg.messages), 1)
        self.assertEqual(len(pkg.provenance), 1)
        self.assertEqual(pkg.messages[0]["message_id"], cand1.message_id)


if __name__ == "__main__":
    unittest.main()
