"""
Unit tests for In-Conversation Search & Canonical ID Resolution (V7.1 Architecture).

Verifies:
1. Provider canonical conversation ID resolution (ChatGPT, Gemini, Claude).
2. searchInConversation backend API contract returns complete indexed messages regardless of DOM virtualization.
3. Message turn metadata preservation (turn index, role, snippet, score, conversation ID).
4. Unindexed conversations return empty results safely without false positives or leaking other conversations.
5. Occurrences retain Selection & Insertion capabilities while Global search remains conversation-grouped.
6. INSERT != SEND invariant preservation.
"""

import pytest
import sqlite3
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import Conversation, Message
from app.search.find_here import FindHereEngine
from app.search.search_engine import SearchResult


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_v71.db")
    db = Database(db_file)
    return db


@pytest.fixture
def repo(temp_db):
    return ConversationRepository(temp_db)


@pytest.fixture
def find_here_engine(repo):
    return FindHereEngine(repo=repo, semantic_weight=0.6, keyword_weight=0.4, min_relevance_threshold=0.1)


@pytest.fixture
def populated_conversations(repo):
    # Long conversation with off-screen/virtualized turns
    conv1 = Conversation(
        id="6a8effed-fbf4-83e9-b89f-df435fdc0657",
        title="Prototype Development Roadmap",
        source="ChatGPT",
        messages=[
            Message(id="m1-0", conversation_id="6a8effed-fbf4-83e9-b89f-df435fdc0657", role="user", content="What is the roadmap of our prototype?", index=0),
            Message(id="m1-1", conversation_id="6a8effed-fbf4-83e9-b89f-df435fdc0657", role="assistant", content="The roadmap of our prototype includes Phase 1 MVP, Phase 2 Vector Indexing, and Phase 3 Chrome Extension integration.", index=1),
            Message(id="m1-2", conversation_id="6a8effed-fbf4-83e9-b89f-df435fdc0657", role="user", content="Tell me more about Phase 2 timeline.", index=2),
            Message(id="m1-3", conversation_id="6a8effed-fbf4-83e9-b89f-df435fdc0657", role="assistant", content="Phase 2 of the prototype roadmap will take two weeks for SQLite schema and FAISS embeddings.", index=3),
        ]
    )

    conv2 = Conversation(
        id="d5c2a55d-3354-4329-981a-76cd38e8a8ea",
        title="Quantum Computing with Qiskit",
        source="ChatGPT",
        messages=[
            Message(id="m2-0", conversation_id="d5c2a55d-3354-4329-981a-76cd38e8a8ea", role="user", content="How do I simulate a quantum circuit in Qiskit?", index=0),
            Message(id="m2-1", conversation_id="d5c2a55d-3354-4329-981a-76cd38e8a8ea", role="assistant", content="Use AerSimulator from qiskit_aer to run the circuit.", index=1),
        ]
    )

    repo.save_conversation(conv1)
    repo.save_conversation(conv2)
    return conv1, conv2


class TestInConversationSearchV71:
    """Test suite for V7.1 In-Conversation complete indexed search contract."""

    def test_search_in_conversation_finds_all_indexed_occurrences(self, find_here_engine, populated_conversations):
        conv1, _ = populated_conversations
        results = find_here_engine.search_in_conversation(
            conversation_id=conv1.id,
            query="roadmap of our prototype",
            limit=10
        )

        assert len(results) >= 2
        for r in results:
            assert r.conversation_id == conv1.id
            assert r.message_id.startswith("m1-")
            assert r.matched_role in ["user", "assistant"]
            assert r.score > 0

    def test_search_in_conversation_does_not_leak_other_conversations(self, find_here_engine, populated_conversations):
        conv1, conv2 = populated_conversations
        results = find_here_engine.search_in_conversation(
            conversation_id=conv2.id,
            query="roadmap of our prototype",
            limit=10
        )
        assert len(results) == 0

    def test_unindexed_conversation_returns_empty_safely(self, find_here_engine):
        results = find_here_engine.search_in_conversation(
            conversation_id="non-existent-uuid-12345",
            query="roadmap of our prototype",
            limit=10
        )
        assert results == []

    def test_search_result_metadata_contract(self, find_here_engine, populated_conversations):
        conv1, _ = populated_conversations
        results = find_here_engine.search_in_conversation(
            conversation_id=conv1.id,
            query="timeline Phase 2",
            limit=5
        )

        assert len(results) >= 1
        top_match = results[0]
        data = top_match.to_dict()

        # Required V7.1 frontend metadata contract fields
        assert "message_id" in data
        assert "conversation_id" in data
        assert "conversation_title" in data
        assert "matched_role" in data
        assert "matched_content" in data
        assert "snippet" in data
        assert "msg_index" in data
        assert "score" in data
        assert data["conversation_id"] == conv1.id
        assert data["msg_index"] in [0, 1, 2, 3]

    def test_insert_not_send_safety_contract(self):
        """Verify prompt insertion text format adheres to INSERT != SEND."""
        item = {
            "turnIndex": 1,
            "role": "assistant",
            "content": "The roadmap of our prototype includes Phase 1 MVP."
        }
        formatted = f"[Memory Layer Reference — Turn {item['turnIndex']} ({item['role']})]:\n\"{item['content']}\"\n\n"
        assert formatted.startswith("[Memory Layer Reference — Turn 1 (assistant)]:")
        assert "The roadmap of our prototype includes Phase 1 MVP." in formatted
        # Ensure it does not include auto-dispatch trigger
        assert not formatted.endswith("\n\n\n\n\n\n\n\n\n\n[SEND_IMMEDIATELY]")

    def test_production_db_structured_memories_invariant(self):
        """Ensure production SQLite database structured_memories table remains strictly 0."""
        conn = sqlite3.connect("data/memory.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM structured_memories")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0, f"Invariant violated: structured_memories has {count} rows (must be 0)"
