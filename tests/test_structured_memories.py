"""
Milestone V6.5-E1: Structured Memories Tests.

Verifies:
1. Single-Message Provenance: Creating, saving, and verifying a memory derived from a single turn.
2. Multi-Message Provenance: Creating, saving, and verifying a memory derived from a multi-turn span.
3. Strict Provenance Validation: Rejecting invalid message IDs, cross-conversation IDs, invalid ranges, and count mismatches.
4. Cascade Deletion: Verifying that deleting a conversation via ConversationRepository automatically removes all child structured memories.
5. Deterministic Extraction: Verifying rule-based offline extraction and persistence.
6. Memory Filtering & Individual Deletion: Filtering by type/status and individual deletion.
"""

import unittest
import os
import sqlite3
from app.models.schemas import Conversation, Message, StructuredMemory
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.structured_memory_repository import StructuredMemoryRepository, ProvenanceValidationError
from app.services.memory_extractor import DeterministicMemoryExtractor


class TestStructuredMemories(unittest.TestCase):
    """Test suite for V6.5-E1 Structured Memories Storage, Provenance & Deletion."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join("data", "test_v65_memories.db")
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

        cls.db = Database(cls.db_path)
        cls.conv_repo = ConversationRepository(cls.db)
        cls.memory_repo = StructuredMemoryRepository(cls.db)
        cls.extractor = DeterministicMemoryExtractor()

        # Create Primary Test Conversation A
        cls.conv_a = Conversation(
            id="conv-arch-decisions",
            title="System Architecture Decisions",
            source="ChatGPT",
            messages=[
                Message(
                    id="msg-a-0",
                    role="user",
                    content="How should we implement lexical ranking normalization?",
                    index=0,
                ),
                Message(
                    id="msg-a-1",
                    role="assistant",
                    content="I recommend we use Okapi BM25 with k1=1.2 and b=0.75 for length normalization.",
                    index=1,
                ),
                Message(
                    id="msg-a-2",
                    role="user",
                    content="Yes, approved! Let's use BM25 for all search queries.",
                    index=2,
                ),
                Message(
                    id="msg-a-3",
                    role="user",
                    content="I prefer dark mode UI for all code editors.",
                    index=3,
                ),
                Message(
                    id="msg-a-4",
                    role="user",
                    content="Project goal: achieve sub-50ms hybrid retrieval latency.",
                    index=4,
                ),
            ],
        )

        # Create Secondary Test Conversation B (for cross-conversation validation checks)
        cls.conv_b = Conversation(
            id="conv-secondary-b",
            title="Secondary Data Processing",
            source="Gemini",
            messages=[
                Message(
                    id="msg-b-0",
                    role="user",
                    content="What is the database configuration?",
                    index=0,
                ),
            ],
        )

        cls.conv_repo.save_conversation(cls.conv_a)
        cls.conv_repo.save_conversation(cls.conv_b)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db") and cls.db:
            cls.db.get_connection().close()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_single_message_provenance_save_and_resolve(self):
        """TEST 01: Single-message memory correctly saves, validates provenance, and resolves raw source message."""
        mem = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="preference",
            content="User prefers dark mode UI for all code editors.",
            start_msg_index=3,
            end_msg_index=3,
            source_message_ids=["msg-a-3"],
            provider="ChatGPT",
            confidence=1.0,
            status="active",
        )

        saved_id = self.memory_repo.save_memory(mem)
        self.assertEqual(saved_id, mem.id)

        # Retrieve and verify fields
        retrieved = self.memory_repo.get_memory(mem.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.conversation_id, "conv-arch-decisions")
        self.assertEqual(retrieved.memory_type, "preference")
        self.assertEqual(retrieved.start_msg_index, 3)
        self.assertEqual(retrieved.end_msg_index, 3)
        self.assertEqual(retrieved.source_message_ids, ["msg-a-3"])

        # Resolve raw backing message
        raw_msgs = self.memory_repo.resolve_provenance_messages(retrieved)
        self.assertEqual(len(raw_msgs), 1)
        self.assertEqual(raw_msgs[0].id, "msg-a-3")
        self.assertIn("dark mode", raw_msgs[0].content)

    def test_02_multi_message_turn_span_provenance(self):
        """TEST 02: Multi-turn memory correctly saves and resolves full sequence of supporting dialogue turns."""
        mem = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="decision",
            content="Adopted Okapi BM25 (k1=1.2, b=0.75) for search query normalization.",
            start_msg_index=0,
            end_msg_index=2,
            source_message_ids=["msg-a-0", "msg-a-1", "msg-a-2"],
            provider="ChatGPT",
            confidence=1.0,
            status="active",
        )

        self.memory_repo.save_memory(mem)
        retrieved = self.memory_repo.get_memory(mem.id)
        self.assertIsNotNone(retrieved)

        raw_msgs = self.memory_repo.resolve_provenance_messages(retrieved)
        self.assertEqual(len(raw_msgs), 3)
        self.assertEqual([m.id for m in raw_msgs], ["msg-a-0", "msg-a-1", "msg-a-2"])
        self.assertEqual(raw_msgs[0].role, "user")
        self.assertEqual(raw_msgs[1].role, "assistant")
        self.assertEqual(raw_msgs[2].role, "user")

    def test_03_strict_provenance_validation_failures(self):
        """TEST 03: StructuredMemoryRepository strictly rejects invalid provenance."""

        # 3A: Non-existent message ID
        mem_invalid_id = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="decision",
            content="Invalid message id test",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-nonexistent-999"],
            provider="ChatGPT",
        )
        with self.assertRaises(ProvenanceValidationError):
            self.memory_repo.save_memory(mem_invalid_id)

        # 3B: Cross-conversation message ID (msg-b-0 belongs to conv-secondary-b, not conv-arch-decisions)
        mem_cross_conv = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="decision",
            content="Cross conversation test",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-b-0"],
            provider="ChatGPT",
        )
        with self.assertRaises(ProvenanceValidationError):
            self.memory_repo.save_memory(mem_cross_conv)

        # 3C: Invalid turn index range (start > end)
        mem_inverted_range = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="decision",
            content="Inverted range test",
            start_msg_index=3,
            end_msg_index=1,
            source_message_ids=["msg-a-1", "msg-a-2", "msg-a-3"],
            provider="ChatGPT",
        )
        with self.assertRaises(ProvenanceValidationError):
            self.memory_repo.save_memory(mem_inverted_range)

        # 3D: Count mismatch (declared range [0, 2] has 3 messages, but only 2 message IDs provided)
        mem_count_mismatch = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="decision",
            content="Count mismatch test",
            start_msg_index=0,
            end_msg_index=2,
            source_message_ids=["msg-a-0", "msg-a-1"],
            provider="ChatGPT",
        )
        with self.assertRaises(ProvenanceValidationError):
            self.memory_repo.save_memory(mem_count_mismatch)

        # 3E: Non-existent parent conversation
        mem_bad_conv = StructuredMemory(
            conversation_id="conv-nonexistent-xyz",
            memory_type="decision",
            content="Bad conv test",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-a-0"],
            provider="ChatGPT",
        )
        with self.assertRaises(ProvenanceValidationError):
            self.memory_repo.save_memory(mem_bad_conv)

    def test_04_sqlite_cascade_deletion_verification(self):
        """TEST 04: Deleting parent conversation via ConversationRepository automatically purges all child memories."""
        # Create a dedicated temporary conversation
        temp_conv = Conversation(
            id="conv-temp-cascade",
            title="Temporary Cascade Test",
            source="Claude",
            messages=[
                Message(id="msg-temp-0", role="user", content="We decided to deprecate legacy API v0.", index=0),
                Message(id="msg-temp-1", role="user", content="I prefer automated deployment pipelines.", index=1),
            ],
        )
        self.conv_repo.save_conversation(temp_conv)

        # Attach 2 structured memories
        mem1 = StructuredMemory(
            conversation_id="conv-temp-cascade",
            memory_type="decision",
            content="Deprecate legacy API v0.",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-temp-0"],
            provider="Claude",
        )
        mem2 = StructuredMemory(
            conversation_id="conv-temp-cascade",
            memory_type="preference",
            content="Automated deployment pipelines preference.",
            start_msg_index=1,
            end_msg_index=1,
            source_message_ids=["msg-temp-1"],
            provider="Claude",
        )
        self.memory_repo.save_memory(mem1)
        self.memory_repo.save_memory(mem2)

        # Assert memories exist
        mems_before = self.memory_repo.list_memories_for_conversation("conv-temp-cascade")
        self.assertEqual(len(mems_before), 2)

        # Execute conversation deletion through standard ConversationRepository path
        deleted = self.conv_repo.delete_conversation("conv-temp-cascade")
        self.assertTrue(deleted)

        # Assert all child structured memories were purged automatically by SQLite cascade
        mems_after = self.memory_repo.list_memories_for_conversation("conv-temp-cascade")
        self.assertEqual(len(mems_after), 0, "All structured memories must be purged when parent conversation is deleted")

        # Direct database assertion
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM structured_memories WHERE conversation_id = ?", ("conv-temp-cascade",))
            count = cursor.fetchone()["cnt"]
            self.assertEqual(count, 0)

    def test_05_deterministic_extractor_extraction_and_filtering(self):
        """TEST 05: Offline DeterministicMemoryExtractor extracts memories and filters by type/status cleanly."""
        extracted = self.extractor.extract_memories(self.conv_a)
        self.assertGreater(len(extracted), 0)

        # Save all extracted memories
        for mem in extracted:
            self.memory_repo.save_memory(mem, validate=True)

        # Query filtered by type
        preferences = self.memory_repo.list_memories_for_conversation("conv-arch-decisions", memory_type="preference")
        self.assertGreaterEqual(len(preferences), 1)
        for p in preferences:
            self.assertEqual(p.memory_type, "preference")

        goals = self.memory_repo.list_memories_for_conversation("conv-arch-decisions", memory_type="project_goal")
        self.assertGreaterEqual(len(goals), 1)
        for g in goals:
            self.assertEqual(g.memory_type, "project_goal")

    def test_06_memory_deletion_and_status(self):
        """TEST 06: Individual structured memory can be deleted and queried by status."""
        mem = StructuredMemory(
            conversation_id="conv-arch-decisions",
            memory_type="fact",
            content="Historical note on previous architecture",
            start_msg_index=1,
            end_msg_index=1,
            source_message_ids=["msg-a-1"],
            provider="ChatGPT",
            status="archived",
        )
        self.memory_repo.save_memory(mem)

        archived = self.memory_repo.list_memories_for_conversation("conv-arch-decisions", status="archived")
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].id, mem.id)

        # Delete individual memory
        deleted = self.memory_repo.delete_memory(mem.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.memory_repo.get_memory(mem.id))


if __name__ == "__main__":
    unittest.main()
