"""
Milestone V6.4-C: Contextual Result Expansion Unit & Integration Test Suite.

Verifies:
1. Short message adaptive expansion (e.g. 'Seee' captures preceding issue & subsequent resolution).
2. Normal and long message turn expansion.
3. Conversation boundary handling (index 0 start, index N-1 end).
4. Single-message conversation graceful fallback.
5. Strict ordering (msg_index ASC) and duplicate prevention.
6. Role and timestamp preservation across AI providers (ChatGPT, Gemini, Claude).
7. Isolation of 'Search This Conversation' vs 'Global Search'.
8. Backward compatibility of SearchResult dataclass and to_dict().
9. Configurable expansion strategies ('adaptive', 'turn_aware', 'fixed').
10. QISE empirical validation (Rank #1 match contains rich surrounding dialogue).
"""

import unittest
import os
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.search.find_here import FindHereEngine
from app.search.context_expander import ContextExpander
from app.search.search_engine import SearchResult


class TestContextualResultExpansion(unittest.TestCase):
    """Comprehensive test suite for V6.4-C Contextual Result Expansion."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join("data", "test_v64c_expansion.db")
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

        cls.db = Database(cls.db_path)
        cls.repo = ConversationRepository(cls.db)
        cls.expander = ContextExpander(cls.repo)
        cls.hybrid = HybridSearchEngine(cls.repo)
        cls.find_here = FindHereEngine(cls.repo)

        # 1. Multi-turn QISE Conversation (Reproducing the QISE "Seee" scenario)
        cls.qise_conv = Conversation(
            id="test-qise-conv-1",
            title="QISE Student Brand Ambassador",
            source="ChatGPT",
            category="Ambassador Program",
            tags=["QISE", "Ambassador", "Support"],
            messages=[
                Message(
                    id="qise-msg-0",
                    role="user",
                    content="Actually I joined a person he is saying lectures are not opening, either tho he completed pre survey form",
                    index=0,
                    timestamp="2026-08-20T10:00:00Z",
                ),
                Message(
                    id="qise-msg-1",
                    role="assistant",
                    content="From the screenshot, the issue is not with the referral or registration. The page clearly shows Lesson content locked. You have a previous lesson that has not been completed.",
                    index=1,
                    timestamp="2026-08-20T10:01:00Z",
                ),
                Message(
                    id="qise-msg-2",
                    role="user",
                    content="Seee",
                    index=2,
                    timestamp="2026-08-20T10:02:00Z",
                ),
                Message(
                    id="qise-msg-3",
                    role="assistant",
                    content="Yes, I can see the issue. The Google Form says: You have already responded. So the survey submission was recorded successfully. Contact QISE support with your registered email.",
                    index=3,
                    timestamp="2026-08-20T10:03:00Z",
                ),
                Message(
                    id="qise-msg-4",
                    role="user",
                    content="I want to ask shreya mam from his side.",
                    index=4,
                    timestamp="2026-08-20T10:04:00Z",
                ),
                Message(
                    id="qise-msg-5",
                    role="assistant",
                    content="You can send Shreya ma'am a polite message: Hi Shreya Ma'am, I referred a student to the QISE course...",
                    index=5,
                    timestamp="2026-08-20T10:05:00Z",
                ),
            ],
        )

        # 2. Gemini Multi-turn Strategy Conversation
        cls.gemini_conv = Conversation(
            id="test-gemini-conv-2",
            title="Gemini Architecture Strategy",
            source="Gemini",
            category="Engineering",
            tags=["Gemini", "Architecture"],
            messages=[
                Message(
                    id="gem-msg-0",
                    role="user",
                    content="What is our cross-AI retrieval approach for Gemini?",
                    index=0,
                    timestamp="2026-08-21T11:00:00Z",
                ),
                Message(
                    id="gem-msg-1",
                    role="assistant",
                    content="We use localized REST endpoints and standard MiniLM vector embeddings.",
                    index=1,
                    timestamp="2026-08-21T11:01:00Z",
                ),
            ],
        )

        # 3. Single-message Boundary Conversation
        cls.single_conv = Conversation(
            id="test-single-conv-3",
            title="Isolated Standalone Prompt",
            source="Claude",
            messages=[
                Message(
                    id="single-msg-0",
                    role="user",
                    content="Standalone test instruction without replies.",
                    index=0,
                    timestamp="2026-08-22T08:00:00Z",
                )
            ],
        )

        cls.repo.save_conversation(cls.qise_conv)
        cls.repo.save_conversation(cls.gemini_conv)
        cls.repo.save_conversation(cls.single_conv)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "db") and cls.db:
            cls.db.get_connection().close()
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    # TEST 1: QISE "Seee" Short Message Adaptive Expansion
    def test_01_qise_short_message_expansion(self):
        """Short message 'Seee' (index 2) expands to capture surrounding issue (msg 1) and resolution (msg 3)."""
        raw_res = SearchResult(
            message_id="qise-msg-2",
            conversation_id="test-qise-conv-1",
            conversation_title="QISE Student Brand Ambassador",
            source="ChatGPT",
            imported_at="2026-08-20T10:02:00Z",
            matched_role="user",
            matched_content="Seee",
            snippet="Seee",
            msg_index=2,
            score=90,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        
        # Verify context_messages populated
        self.assertGreater(len(expanded.context_messages), 1)
        indices = [m["msg_index"] for m in expanded.context_messages]
        self.assertIn(1, indices, "Should include preceding assistant message")
        self.assertIn(2, indices, "Should include matched user message")
        self.assertIn(3, indices, "Should include following assistant resolution")

        # Verify context_text formatting
        self.assertIn("Lesson content locked", expanded.context_text)
        self.assertIn("Seee", expanded.context_text)
        self.assertIn("Google Form", expanded.context_text)
        self.assertIn("User: Seee", expanded.context_text)

    # TEST 2: Conversation Start Boundary (msg_index = 0)
    def test_02_conversation_start_boundary(self):
        """Match at msg_index = 0 begins safely at index 0 without negative slicing."""
        raw_res = SearchResult(
            message_id="qise-msg-0",
            conversation_id="test-qise-conv-1",
            conversation_title="QISE Student Brand Ambassador",
            source="ChatGPT",
            imported_at="2026-08-20T10:00:00Z",
            matched_role="user",
            matched_content="Actually I joined a person he is saying lectures are not opening...",
            snippet="Actually I joined...",
            msg_index=0,
            score=85,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        self.assertGreater(len(expanded.context_messages), 0)
        self.assertEqual(expanded.context_messages[0]["msg_index"], 0)
        self.assertEqual(expanded.context_messages[0]["role"], "user")

    # TEST 3: Conversation End Boundary (msg_index = N - 1)
    def test_03_conversation_end_boundary(self):
        """Match at msg_index = 5 (last message) ends cleanly without index overflow."""
        raw_res = SearchResult(
            message_id="qise-msg-5",
            conversation_id="test-qise-conv-1",
            conversation_title="QISE Student Brand Ambassador",
            source="ChatGPT",
            imported_at="2026-08-20T10:05:00Z",
            matched_role="assistant",
            matched_content="You can send Shreya ma'am a polite message...",
            snippet="You can send...",
            msg_index=5,
            score=80,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        self.assertGreater(len(expanded.context_messages), 0)
        last_msg = expanded.context_messages[-1]
        self.assertEqual(last_msg["msg_index"], 5)
        # Preceding user message should be included
        self.assertTrue(any(m["msg_index"] == 4 for m in expanded.context_messages))

    # TEST 4: Single-Message Conversation Graceful Fallback
    def test_04_single_message_conversation(self):
        """Conversation with exactly 1 message produces 1 context message without error."""
        raw_res = SearchResult(
            message_id="single-msg-0",
            conversation_id="test-single-conv-3",
            conversation_title="Isolated Standalone Prompt",
            source="Claude",
            imported_at="2026-08-22T08:00:00Z",
            matched_role="user",
            matched_content="Standalone test instruction without replies.",
            snippet="Standalone...",
            msg_index=0,
            score=75,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        self.assertEqual(len(expanded.context_messages), 1)
        self.assertEqual(expanded.context_messages[0]["content"], "Standalone test instruction without replies.")
        self.assertIn("User: Standalone test instruction", expanded.context_text)

    # TEST 5: Strict Ordering and Zero Duplicate Messages
    def test_05_strict_ordering_and_no_duplicates(self):
        """Expanded context messages are strictly ordered msg_index ASC with unique IDs."""
        raw_res = SearchResult(
            message_id="qise-msg-3",
            conversation_id="test-qise-conv-1",
            conversation_title="QISE Student Brand Ambassador",
            source="ChatGPT",
            imported_at="2026-08-20T10:03:00Z",
            matched_role="assistant",
            matched_content="Yes, I can see the issue...",
            snippet="Yes, I can see...",
            msg_index=3,
            score=88,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        msg_ids = [m["id"] for m in expanded.context_messages]
        self.assertEqual(len(msg_ids), len(set(msg_ids)), "Must contain no duplicate messages")

        indices = [m["msg_index"] for m in expanded.context_messages]
        self.assertEqual(indices, sorted(indices), "Indices must be strictly ascending")

    # TEST 6: Role & Source Preservation across Providers
    def test_06_role_and_source_preservation(self):
        """Cross-AI conversation (Gemini) preserves role, provider source, and timestamp."""
        raw_res = SearchResult(
            message_id="gem-msg-0",
            conversation_id="test-gemini-conv-2",
            conversation_title="Gemini Architecture Strategy",
            source="Gemini",
            imported_at="2026-08-21T11:00:00Z",
            matched_role="user",
            matched_content="What is our cross-AI retrieval approach for Gemini?",
            snippet="What is our...",
            msg_index=0,
            score=82,
        )

        expanded = self.expander.expand_single_result(raw_res, strategy="adaptive")
        self.assertEqual(expanded.source, "Gemini")
        self.assertEqual(expanded.context_messages[0]["role"], "user")
        self.assertEqual(expanded.context_messages[1]["role"], "assistant")
        self.assertEqual(expanded.context_messages[0]["timestamp"], "2026-08-21T11:00:00Z")

    # TEST 7: Search This Conversation (FindHereEngine) Scope Isolation
    def test_07_find_here_scoped_expansion(self):
        """In-conversation search results expand strictly within the target conversation."""
        results = self.find_here.search_in_conversation(
            conversation_id="test-qise-conv-1",
            query="lectures survey issue",
            limit=5,
            expand_context=True,
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r.conversation_id, "test-qise-conv-1")
            self.assertGreater(len(r.context_messages), 0)
            for cm in r.context_messages:
                self.assertEqual(cm["conversation_id"], "test-qise-conv-1", "Context must not leak from other conversations")

    # TEST 8: Global Hybrid Search Expansion
    def test_08_global_hybrid_search_expansion(self):
        """Global search enriches top results while preserving score ranking."""
        results = self.hybrid.search("cross-AI retrieval Gemini approach", limit=5, expand_context=True)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top.conversation_title, "Gemini Architecture Strategy")
        self.assertGreater(len(top.context_messages), 0)
        self.assertIn("User:", top.context_text)
        self.assertIn("Assistant:", top.context_text)

    # TEST 9: Configurable Strategies Comparison ('fixed', 'turn_aware', 'adaptive')
    def test_09_configurable_strategies(self):
        """Verify behavior across all 3 configurable strategies."""
        res_fixed = SearchResult(
            message_id="qise-msg-2",
            conversation_id="test-qise-conv-1",
            conversation_title="QISE",
            source="ChatGPT",
            imported_at="",
            matched_role="user",
            matched_content="Seee",
            snippet="Seee",
            msg_index=2,
        )
        exp_fixed = self.expander.expand_single_result(res_fixed, strategy="fixed", window_size=1)
        self.assertEqual(len(exp_fixed.context_messages), 3)  # index 1, 2, 3

        res_turn = SearchResult(
            message_id="gem-msg-0",
            conversation_id="test-gemini-conv-2",
            conversation_title="Gemini",
            source="Gemini",
            imported_at="",
            matched_role="user",
            matched_content="What is our cross-AI retrieval approach?",
            snippet="",
            msg_index=0,
        )
        exp_turn = self.expander.expand_single_result(res_turn, strategy="turn_aware", window_size=1)
        self.assertEqual(len(exp_turn.context_messages), 2)  # index 0, 1

    # TEST 10: Backward-Compatible to_dict() Serialization
    def test_10_backward_compatible_serialization(self):
        """SearchResult.to_dict() retains all legacy keys and exposes new context keys."""
        res = SearchResult(
            message_id="msg-1",
            conversation_id="conv-1",
            conversation_title="Title",
            source="ChatGPT",
            imported_at="2026-08-20",
            matched_role="user",
            matched_content="Hello",
            snippet="Hello",
            msg_index=0,
            category="Tech",
            tags=["AI"],
            score=95,
            context_messages=[{"role": "user", "content": "Hello"}],
            context_text="User: Hello",
        )
        d = res.to_dict()

        # Legacy fields
        self.assertEqual(d["message_id"], "msg-1")
        self.assertEqual(d["conversation_id"], "conv-1")
        self.assertEqual(d["conversation_title"], "Title")
        self.assertEqual(d["source"], "ChatGPT")
        self.assertEqual(d["matched_role"], "user")
        self.assertEqual(d["matched_content"], "Hello")
        self.assertEqual(d["score"], 95)

        # New V6.4-C fields
        self.assertIn("context_messages", d)
        self.assertIn("context_text", d)
        self.assertEqual(d["context_text"], "User: Hello")


if __name__ == "__main__":
    unittest.main()
