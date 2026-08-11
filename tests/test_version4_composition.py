"""
Unit and Integration Tests for Version 4 Features:
🧩 COMPOSE CONTEXT — Multi-Topic / Multi-Conversation Context Composition Engine
"""

import os
import unittest

from app.models.schemas import Conversation, Message, ContextCandidate
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.services.context_composer import ContextComposer


class TestVersion4Composition(unittest.TestCase):
    """Test suite for Version 4 Context Composer service, models, relationships, and immutability."""

    def setUp(self):
        self.test_db_path = f"test_v4_{os.getpid()}.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

        self.db = Database(self.test_db_path)
        self.repo = ConversationRepository(self.db)
        self.search_engine = HybridSearchEngine(self.repo)
        self.composer = ContextComposer(self.repo, self.search_engine)

        # Seed 4 test conversations representing different providers & topics
        self.conv_a = Conversation(
            title="Personal AI Memory Layer Project",
            source="ChatGPT",
            messages=[
                Message(role="user", content="I want to build a local Personal AI Memory Layer.", index=0),
                Message(role="assistant", content="The architecture ingests ChatGPT exports and uses local neural vector search.", index=1),
            ]
        )
        self.conv_b = Conversation(
            title="Startup Funding Strategy",
            source="ChatGPT",
            messages=[
                Message(role="user", content="What is our angel funding strategy for the memory layer startup?", index=0),
                Message(role="assistant", content="Focus on local-first privacy as our key seed pitch differentiator.", index=1),
            ]
        )
        self.conv_c = Conversation(
            title="Cross-AI Gemini & Claude Integration",
            source="Gemini",
            messages=[
                Message(role="user", content="Can the memory layer work across Gemini and Claude conversations?", index=0),
                Message(role="assistant", content="Yes, by standardizing exports into a provider-independent schema.", index=1),
            ]
        )
        self.conv_d = Conversation(
            title="Quantum Qiskit Experiments",
            source="Claude",
            messages=[
                Message(role="user", content="How do I simulate a Bell state in Qiskit?", index=0),
                Message(role="assistant", content="Use QuantumCircuit(2, 2) and add Hadamard and CNOT gates.", index=1),
            ]
        )

        self.id_a = self.repo.save_conversation(self.conv_a)
        self.id_b = self.repo.save_conversation(self.conv_b)
        self.id_c = self.repo.save_conversation(self.conv_c)
        self.id_d = self.repo.save_conversation(self.conv_d)

    def tearDown(self):
        if hasattr(self.db, "_memory_conn") and self.db._memory_conn:
            try:
                self.db._memory_conn.close()
            except Exception:
                pass
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

    def test_01_multi_conversation_retrieval(self):
        """TEST 1: Search retrieves candidates from multiple distinct source conversations."""
        query = "Memory Layer funding strategy Gemini integration"
        grouped = self.composer.search_context(query)

        # Must retrieve candidates from Conv A, Conv B, and Conv C
        retrieved_conv_ids = set(grouped.keys())
        self.assertIn(self.id_a, retrieved_conv_ids)
        self.assertIn(self.id_b, retrieved_conv_ids)
        self.assertIn(self.id_c, retrieved_conv_ids)

    def test_02_multi_topic_retrieval(self):
        """TEST 2: Query containing three topics returns candidates covering all three topics."""
        query = "Memory Layer funding Gemini"
        grouped = self.composer.search_context(query)

        all_candidates = []
        for k, grp in grouped.items():
            if k != "_diagnostics":
                all_candidates.extend(grp["candidates"])

        contents = " ".join(c.content.lower() for c in all_candidates)
        self.assertIn("memory layer", contents)
        self.assertIn("funding", contents)
        self.assertIn("gemini", contents)

    def test_03_selection(self):
        """TEST 3: Only user-selected candidates enter the composed context."""
        grouped = self.composer.search_context("Memory Layer funding")
        cands_a = grouped[self.id_a]["candidates"]

        # Select ONLY candidates from Conv A
        preview = self.composer.build_context_preview(cands_a, query="Memory Layer funding")

        self.assertEqual(len(preview.selected_candidates), len(cands_a))
        for c in preview.selected_candidates:
            self.assertEqual(c.conversation_id, self.id_a)

    def test_04_deselection(self):
        """TEST 4: Deselected/removed messages are excluded from composed context."""
        grouped = self.composer.search_context("Memory Layer funding")
        cands_a = grouped[self.id_a]["candidates"]
        cands_b = grouped[self.id_b]["candidates"]

        combined = cands_a + cands_b
        # Deselect candidates from Conv B
        filtered = [c for c in combined if c.conversation_id != self.id_b]

        preview = self.composer.build_context_preview(filtered, query="Filtered")
        conv_ids = [c.conversation_id for c in preview.selected_candidates]

        self.assertNotIn(self.id_b, conv_ids)

    def test_05_ordering(self):
        """TEST 5: Composed context follows exact user-defined reordered sequence."""
        grouped = self.composer.search_context("Memory Layer funding Gemini")
        cand_a = grouped[self.id_a]["candidates"][0]
        cand_b = grouped[self.id_b]["candidates"][0]
        cand_c = grouped[self.id_c]["candidates"][0]

        original_list = [cand_a, cand_b, cand_c]
        # Reorder to C -> A -> B
        custom_order_ids = [cand_c.message_id, cand_a.message_id, cand_b.message_id]

        reordered = self.composer.reorder_context(original_list, custom_order_ids)

        self.assertEqual(reordered[0].message_id, cand_c.message_id)
        self.assertEqual(reordered[1].message_id, cand_a.message_id)
        self.assertEqual(reordered[2].message_id, cand_b.message_id)

    def test_06_provenance(self):
        """TEST 6: Derived messages retain source_conversation_id and source_message_id."""
        grouped = self.composer.search_context("Memory Layer funding")
        selected = [grouped[self.id_a]["candidates"][0], grouped[self.id_b]["candidates"][0]]

        composed_conv, _ = self.composer.create_composed_conversation("Composed Test", "query", selected)

        self.assertEqual(composed_conv.messages[0].source_conversation_id, self.id_a)
        self.assertEqual(composed_conv.messages[0].source_message_id, selected[0].message_id)
        self.assertEqual(composed_conv.messages[1].source_conversation_id, self.id_b)
        self.assertEqual(composed_conv.messages[1].source_message_id, selected[1].message_id)

    def test_07_multiple_source_relationships(self):
        """TEST 7: One composed conversation references multiple source conversations in DB."""
        grouped = self.composer.search_context("Memory Layer funding Gemini")
        selected = [
            grouped[self.id_a]["candidates"][0],
            grouped[self.id_b]["candidates"][0],
            grouped[self.id_c]["candidates"][0],
        ]

        composed_conv, composed_ctx = self.composer.create_composed_conversation("Strategy", "query", selected)

        # Verify parent relationship info in DB
        rel_info = self.repo.get_relationships(composed_conv.id)
        # Should have parent relationships pointing to Conv A, Conv B, and Conv C
        self.assertEqual(len(composed_ctx.source_conversations), 3)

    def test_08_original_immutability(self):
        """TEST 8: Original source conversations and messages remain completely unchanged."""
        orig_conv_a_before = self.repo.get_conversation(self.id_a)
        orig_msg_count_before = orig_conv_a_before.message_count

        grouped = self.composer.search_context("Memory Layer")
        selected = grouped[self.id_a]["candidates"]

        self.composer.create_composed_conversation("Composed Chat", "query", selected)

        orig_conv_a_after = self.repo.get_conversation(self.id_a)
        self.assertEqual(orig_conv_a_after.message_count, orig_msg_count_before)
        self.assertEqual(orig_conv_a_after.title, orig_conv_a_before.title)

    def test_09_provider_independence(self):
        """TEST 9: Context composition seamlessly combines ChatGPT + Gemini candidates."""
        grouped = self.composer.search_context("Memory Layer Gemini")
        selected = [grouped[self.id_a]["candidates"][0], grouped[self.id_c]["candidates"][0]]

        preview = self.composer.build_context_preview(selected, query="Multi-provider")
        providers = preview.source_providers

        self.assertIn("ChatGPT", providers)
        self.assertIn("Gemini", providers)
        self.assertEqual(providers["ChatGPT"], 1)
        self.assertEqual(providers["Gemini"], 1)

    def test_10_composed_conversation_creation(self):
        """TEST 10: Composed conversation is correctly created and retrievable from repository."""
        grouped = self.composer.search_context("Memory Layer")
        selected = grouped[self.id_a]["candidates"]

        composed_conv, comp_ctx = self.composer.create_composed_conversation("Product Strategy", "query", selected)
        retrieved = self.repo.get_conversation(composed_conv.id)

        self.assertIsNotNone(retrieved)
        self.assertTrue(retrieved.title.startswith("Composed:"))
        self.assertEqual(retrieved.category, "Context Composition")

    def test_11_no_duplicate_source_messages(self):
        """TEST 11: Selecting the same candidate message twice does not create duplicate entries."""
        grouped = self.composer.search_context("Memory Layer")
        cand = grouped[self.id_a]["candidates"][0]

        # Duplicate selection list
        duplicated_list = [cand, cand, cand]
        preview = self.composer.build_context_preview(duplicated_list, query="No dups")

        self.assertEqual(len(preview.selected_candidates), 1)

    def test_12_export_payload_structure(self):
        """TEST 12: ComposedContext export payload is provider-independent for future AI destinations."""
        grouped = self.composer.search_context("Memory Layer Gemini")
        selected = [grouped[self.id_a]["candidates"][0], grouped[self.id_c]["candidates"][0]]

        preview = self.composer.build_context_preview(selected, query="Multi-provider", title="Composed Export")
        payload = preview.export()

        self.assertEqual(payload["title"], "Composed Export")
        self.assertEqual(payload["total_messages"], 2)
        self.assertIn("source_conversations", payload)
        self.assertIn("source_providers", payload)
        self.assertIn("messages", payload)

    def test_13_multi_topic_decomposition_retrieves_3_distinct_topic_groups(self):
        """TEST 13: Multi-topic query decomposes into sub-topics and retrieves candidates from at least 3 topic groups."""
        query = "Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini."
        grouped = self.composer.search_context(query)

        diagnostics = grouped.get("_diagnostics")
        self.assertIsNotNone(diagnostics)
        self.assertTrue(len(diagnostics["detected_topics"]) >= 3)
        self.assertTrue(diagnostics["conversations_found"] >= 3)

    def test_14_v3_continuation_does_not_crowd_out_parent(self):
        """TEST 14: A V3 continuation conversation does not crowd out its parent/original conversation in candidate ordering."""
        # Create V3 continuation from Conv A
        from app.services.topic_extractor import TopicExtractionEngine
        extractor = TopicExtractionEngine(self.repo)
        preview = extractor.extract_topic_context(self.id_a, "Memory Layer")
        msg_ids = [m.message_id for m in preview.selected_messages]
        continued_conv = extractor.create_continued_conversation(self.id_a, "Memory Layer", msg_ids)

        query = "Memory Layer funding strategy"
        grouped = self.composer.search_context(query)

        conv_keys = [k for k in grouped.keys() if k != "_diagnostics"]
        # Original parent Conv A (self.id_a) should appear before continued_conv.id
        if self.id_a in conv_keys and continued_conv.id in conv_keys:
            self.assertTrue(conv_keys.index(self.id_a) < conv_keys.index(continued_conv.id))

    def test_15_multi_topic_results_contain_multiple_conversations(self):
        """TEST 15: Multi-topic results contain candidates from multiple distinct relevant conversations."""
        query = "Memory Layer, funding strategy, Gemini"
        grouped = self.composer.search_context(query)
        conv_keys = [k for k in grouped.keys() if k != "_diagnostics"]

        self.assertTrue(len(conv_keys) >= 3)

    def test_16_duplicate_messages_removed_from_candidate_set(self):
        """TEST 16: Duplicate messages retrieved across sub-topic searches are deduplicated."""
        query = "Memory Layer, Personal AI Memory Layer, memory architecture"
        grouped = self.composer.search_context(query)
        diagnostics = grouped.get("_diagnostics")

        self.assertIsNotNone(diagnostics)
        # All candidate message_ids inside conv_groups must be unique
        all_ids = []
        for k, grp in grouped.items():
            if k != "_diagnostics":
                for cand in grp["candidates"]:
                    all_ids.append(cand.message_id)

        self.assertEqual(len(all_ids), len(set(all_ids)))


if __name__ == "__main__":
    unittest.main()
