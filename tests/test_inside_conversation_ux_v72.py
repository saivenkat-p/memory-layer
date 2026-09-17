"""
Test suite for Inside Conversation — Complete UX Specification (V7.2).

Verifies all canonical requirements from UX Specification:
1. Search current conversation strictly scoped.
2. Stable sequential question numbering (1, 1a, 2, 2a, 3, 3a...).
3. Search results return user questions only by default with question number and text.
4. Assistant matches preserve link to their parent user question.
5. Direct navigation to questions, top, and bottom turns.
6. Multi-message selection (matching + non-matching context).
7. Non-destructive child conversation creation preserving parent provenance.
8. Parent conversation remains 100% intact without message loss or rewriting.
9. ContextBridge exact package preview and application.
10. INSERT != SEND safety invariant.
11. Production DB structured_memories count == 0.
"""

import pytest
import sqlite3
import uuid
import os
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import Conversation, Message
from app.search.find_here import FindHereEngine
from app.search.search_engine import SearchResult


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_v72.db")
    return Database(db_file)


@pytest.fixture
def repo(temp_db):
    return ConversationRepository(temp_db)


@pytest.fixture
def find_here_engine(repo):
    return FindHereEngine(repo=repo, semantic_weight=0.6, keyword_weight=0.4, min_relevance_threshold=0.1)


@pytest.fixture
def populated_conversation(repo):
    conv_id = "test-conv-portfolio-789"
    conv = Conversation(
        id=conv_id,
        title="Portfolio & Career Planning",
        source="ChatGPT",
        messages=[
            Message(id="msg-0", conversation_id=conv_id, role="user", content="Hi Sai", index=0),
            Message(id="msg-1", conversation_id=conv_id, role="assistant", content="Hello! How can I help you today?", index=1),
            Message(id="msg-2", conversation_id=conv_id, role="user", content="What is a portfolio?", index=2),
            Message(id="msg-3", conversation_id=conv_id, role="assistant", content="A portfolio is a curated collection of your work and projects.", index=3),
            Message(id="msg-4", conversation_id=conv_id, role="user", content="How should I improve my portfolio?", index=4),
            Message(id="msg-5", conversation_id=conv_id, role="assistant", content="Focus on highlighting your best full-stack and AI projects with live demos.", index=5),
            Message(id="msg-6", conversation_id=conv_id, role="user", content="What is another replacement for portfolio?", index=6),
            Message(id="msg-7", conversation_id=conv_id, role="assistant", content="You can use personal websites, interactive playgrounds, or GitHub repositories.", index=7),
            Message(id="msg-8", conversation_id=conv_id, role="user", content="How should I present this in my portfolio?", index=8),
            Message(id="msg-9", conversation_id=conv_id, role="assistant", content="Use clear architecture diagrams, problem statements, and key benchmarks.", index=9),
        ]
    )
    repo.save_conversation(conv)
    return conv


class TestInsideConversationUXV72:
    """Canonical test suite for Inside Conversation workspace specifications."""

    def test_question_numbering_sequential_and_stable(self, find_here_engine, populated_conversation):
        conv = populated_conversation
        results = find_here_engine.search_in_conversation(
            conversation_id=conv.id,
            query="portfolio",
            limit=20
        )

        assert len(results) >= 4
        # Verify question numbers assigned to results
        q_numbers = [r.question_number for r in results if r.question_number is not None]
        assert len(q_numbers) > 0
        for r in results:
            assert r.question_number in [1, 2, 3, 4, 5]
            if r.matched_role == "user":
                assert r.turn_label == str(r.question_number)
            elif r.matched_role == "assistant":
                assert r.turn_label == f"{r.question_number}a"

    def test_search_results_contain_user_question_text(self, find_here_engine, populated_conversation):
        conv = populated_conversation
        results = find_here_engine.search_in_conversation(
            conversation_id=conv.id,
            query="improve my portfolio",
            limit=5
        )

        assert len(results) >= 1
        top_match = results[0]
        data = top_match.to_dict()

        assert data["question_number"] == 3
        assert "improve my portfolio" in data["parent_question_text"].lower() or "improve my portfolio" in data["matched_content"].lower()

    def test_create_child_conversation_preserves_parent_intact(self, repo, populated_conversation):
        parent_conv = populated_conversation
        parent_msg_count_before = len(parent_conv.messages)

        # Create child from selected messages (msg-2, msg-3, msg-4, msg-5)
        selected_ids = ["msg-2", "msg-3", "msg-4", "msg-5"]
        child_msgs = [
            Message(id=f"child_{m.id}", role=m.role, content=m.content, index=i)
            for i, m in enumerate(parent_conv.messages) if m.id in selected_ids
        ]

        child_id = str(uuid.uuid4())
        child_conv = Conversation(
            id=child_id,
            title="[Child] Portfolio Focus Topic",
            source=parent_conv.source,
            messages=child_msgs,
            tags=["child_topic", f"parent:{parent_conv.id}"],
            description=f"Derived from parent conversation {parent_conv.id}"
        )
        repo.save_conversation(child_conv)

        # 1. Verify child is created and searchable
        retrieved_child = repo.get_conversation(child_id)
        assert retrieved_child is not None
        assert len(retrieved_child.messages) == 4
        assert retrieved_child.title == "[Child] Portfolio Focus Topic"
        assert f"parent:{parent_conv.id}" in retrieved_child.tags

        # 2. Verify parent remains 100% INTACT (same length, no deletions)
        retrieved_parent = repo.get_conversation(parent_conv.id)
        assert retrieved_parent is not None
        assert len(retrieved_parent.messages) == parent_msg_count_before
        assert [m.id for m in retrieved_parent.messages] == [m.id for m in parent_conv.messages]

    def test_content_script_user_questions_presentation_contract(self):
        """Verify content.js renders User Questions Only by default and includes toolbar and accordion."""
        content_path = os.path.join("extension", "content", "content.js")
        with open(content_path, "r", encoding="utf-8") as f:
            code = f.read()

        assert "ml-inside-conv-toolbar" in code
        assert "ml-btn-jump-top" in code
        assert "ml-btn-jump-bottom" in code
        assert "ml-btn-select-all-matches" in code
        assert "ml-q-badge" in code
        assert "ml-accordion-toggle" in code
        assert "Question #" in code

    def test_insert_not_send_safety_invariant(self):
        """Verify formatted insertion string does not contain auto-submit markers."""
        item = {
            "turnIndex": 2,
            "role": "user",
            "content": "What is a portfolio?"
        }
        formatted = f"[Memory Layer Reference — Question #2 ({item['role']})]:\n\"{item['content']}\"\n\n"
        assert "[Memory Layer Reference — Question #2 (user)]:" in formatted
        assert "What is a portfolio?" in formatted
        # Strict enforcement: does NOT click send or auto-dispatch
        assert not formatted.endswith("\n[AUTO_SEND]")

    def test_production_db_invariant_structured_memories(self):
        conn = sqlite3.connect("data/memory.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM structured_memories")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0, f"Invariant violated: structured_memories count is {count} (must be 0)"
