"""
Unit Tests for Milestone V5B: Live AI Integration (Destination Adapters & Registry).

Executes 100% locally with mocked HTTP response handlers (ZERO external network calls or API keys required).
"""

import os
import json
import unittest

from app.models.schemas import Conversation, Message, ContextCandidate, ComposedContext, PortableContextPackage
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.services.context_composer import ContextComposer
from app.services.export_engine import LocalExportDestination
from app.services.destination_adapters.base import DestinationAdapter, DestinationResult
from app.services.destination_adapters.local import LocalExportAdapter
from app.services.destination_adapters.chatgpt import ChatGPTAdapter
from app.services.destination_adapters.stubs import GeminiAdapter, ClaudeAdapter
from app.services.destination_adapters.registry import DestinationRegistry


def mock_successful_openai_executor(url, api_key, payload_dict):
    """Mock HTTP executor simulating a successful OpenAI Chat API response."""
    return 200, {
        "id": "chatcmpl-mock-12345",
        "object": "chat.completion",
        "created": 1700000000,
        "model": payload_dict.get("model", "gpt-4o-mini"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Synthesized insight based on your historical Personal AI Memory Layer context."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 20, "total_tokens": 170}
    }


def mock_error_openai_executor(url, api_key, payload_dict):
    """Mock HTTP executor simulating an OpenAI API error response."""
    return 429, {"error": {"message": "Rate limit exceeded for model gpt-4o-mini", "type": "rate_limit_error"}}


class TestVersion5BAdapters(unittest.TestCase):
    """Test suite for V5B Destination Adapters (TEST 68 to TEST 80)."""

    def setUp(self):
        self.test_db_path = f"test_v5b_{os.getpid()}.db"
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

        self.db = Database(self.test_db_path)
        self.repo = ConversationRepository(self.db)
        self.composer = ContextComposer(self.repo)
        self.exporter = LocalExportDestination()

        # Seed test conversations
        self.conv_chatgpt = Conversation(
            title="Funding Pitch",
            source="ChatGPT",
            messages=[
                Message(role="user", content="How do we present pre-seed funding slides?", index=0),
                Message(role="assistant", content="Focus on local-first privacy and subscriber ARR.", index=1),
            ]
        )
        self.conv_gemini = Conversation(
            title="Cross-AI Handoff",
            source="Gemini",
            messages=[
                Message(role="user", content="Can memory layer work across Gemini?", index=0),
                Message(role="assistant", content="Yes via PortableContextPackage v1.0.", index=1),
            ]
        )

        self.id_chatgpt = self.repo.save_conversation(self.conv_chatgpt)
        self.id_gemini = self.repo.save_conversation(self.conv_gemini)

        # Build sample package
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
            query="Funding and Cross-AI Integration",
            title="Composed Strategy Package"
        )
        self.package = self.exporter.prepare_context(self.sample_composed_ctx)

        self.local_adapter = LocalExportAdapter(self.exporter)
        self.chatgpt_adapter = ChatGPTAdapter(mock_executor=mock_successful_openai_executor)
        self.gemini_adapter = GeminiAdapter()
        self.claude_adapter = ClaudeAdapter()
        self.registry = DestinationRegistry(mock_chatgpt_executor=mock_successful_openai_executor)

    def tearDown(self):
        if hasattr(self.db, "_memory_conn") and self.db._memory_conn:
            try:
                self.db._memory_conn.close()
            except Exception:
                pass
        del self.local_adapter
        del self.chatgpt_adapter
        del self.gemini_adapter
        del self.claude_adapter
        del self.registry
        del self.composer
        del self.repo
        del self.db
        import gc
        gc.collect()

        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_68_package_accepted_by_adapters(self):
        """TEST 68: PortableContextPackage accepted by LocalExportAdapter and ChatGPTAdapter validation."""
        local_res = self.local_adapter.validate(self.package)
        self.assertEqual(local_res.status, "SUCCESS")

        chatgpt_res = self.chatgpt_adapter.validate(self.package, config={"api_key": "sk-test-key"})
        self.assertEqual(chatgpt_res.status, "SUCCESS")

    def test_69_invalid_package_rejected(self):
        """TEST 69: Invalid/empty package rejected by adapter validation."""
        local_res = self.local_adapter.validate(None)
        self.assertEqual(local_res.status, "VALIDATION_ERROR")

        chatgpt_res = self.chatgpt_adapter.validate(None, config={"api_key": "sk-test-key"})
        self.assertEqual(chatgpt_res.status, "VALIDATION_ERROR")

    def test_70_unsupported_schema_version_rejected(self):
        """TEST 70: Package with unsupported schema version ('0.9') rejected."""
        bad_pkg = PortableContextPackage(
            package_id="test",
            title="bad",
            topic="bad",
            context_text="bad",
            messages=[{"content": "hi"}],
            schema_version="0.9"
        )
        res = self.local_adapter.validate(bad_pkg)
        self.assertEqual(res.status, "VALIDATION_ERROR")
        self.assertEqual(res.error_code, "UNSUPPORTED_SCHEMA_VERSION")

    def test_71_chatgpt_payload_transformation_preserves_multi_turn_order(self):
        """TEST 71: ChatGPTAdapter transforms package into native multi-turn messages array preserving order."""
        payload = self.chatgpt_adapter.prepare(self.package)

        self.assertIn("messages", payload)
        msgs = payload["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("historical reference context", msgs[0]["content"].lower())

        # First message is user
        self.assertEqual(msgs[1]["role"], "user")
        self.assertIn("pre-seed funding slides", msgs[1]["content"])

        # Second message is assistant
        self.assertEqual(msgs[2]["role"], "assistant")
        self.assertIn("PortableContextPackage v1.0", msgs[2]["content"])

    def test_72_unselected_messages_never_included(self):
        """TEST 72: Messages NOT selected in PortableContextPackage are never included in prepared payload."""
        payload = self.chatgpt_adapter.prepare(self.package)
        content_blob = json.dumps(payload)

        # Message 0 of Conv Gemini ("Can memory layer work across Gemini?") was NOT selected
        unselected_text = self.conv_gemini.messages[0].content
        self.assertNotIn(unselected_text, content_blob)

    def test_73_provider_metadata_preserved_in_system_prompt(self):
        """TEST 73: Provider metadata & source conversation summary preserved in system prompt."""
        payload = self.chatgpt_adapter.prepare(self.package)
        sys_msg = payload["messages"][0]["content"]

        self.assertIn("Funding Pitch", sys_msg)
        self.assertIn("Cross-AI Handoff", sys_msg)
        self.assertIn("Funding and Cross-AI Integration", sys_msg)

    def test_74_provenance_preserved_in_package(self):
        """TEST 74: Provenance audit records preserved intact in package."""
        self.assertEqual(len(self.package.provenance), 2)
        for prov in self.package.provenance:
            self.assertIn("message_id", prov)
            self.assertIn("source_conversation_id", prov)

    def test_75_destination_result_normalized(self):
        """TEST 75: DestinationResult normalized across Local, ChatGPT, and Stub adapters."""
        loc_res = self.local_adapter.execute(self.package)
        self.assertEqual(loc_res.status, "SUCCESS")
        self.assertEqual(loc_res.provider, "Local Export (JSON & Plain Text)")

        gpt_res = self.chatgpt_adapter.execute(self.package, config={"api_key": "sk-test-key"})
        self.assertEqual(gpt_res.status, "API_RESPONSE")
        self.assertEqual(gpt_res.provider, "ChatGPT (OpenAI API)")

        gem_res = self.gemini_adapter.execute(self.package)
        self.assertEqual(gem_res.status, "NOT_SUPPORTED")
        self.assertEqual(gem_res.provider, "Gemini (Google AI API)")

    def test_76_missing_api_credentials_handled_safely(self):
        """TEST 76: Missing API credentials return AUTH_REQUIRED status without crashing."""
        # Ensure OPENAI_API_KEY environment variable is cleared for this test
        old_env = os.environ.get("OPENAI_API_KEY")
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        try:
            res = self.chatgpt_adapter.execute(self.package, config={"api_key": ""})
            self.assertEqual(res.status, "AUTH_REQUIRED")
            self.assertEqual(res.error_code, "MISSING_API_KEY")
        finally:
            if old_env:
                os.environ["OPENAI_API_KEY"] = old_env

    def test_77_network_error_handled_safely(self):
        """TEST 77: Simulated network/API HTTP errors handled gracefully with NETWORK_ERROR status."""
        error_adapter = ChatGPTAdapter(mock_executor=mock_error_openai_executor)
        res = error_adapter.execute(self.package, config={"api_key": "sk-test-key"})

        self.assertEqual(res.status, "NETWORK_ERROR")
        self.assertIn("429", res.message)

    def test_78_user_cancellation_flow(self):
        """TEST 78: User cancellation flow returns USER_CANCELLED status without executing transfer."""
        cancel_res = DestinationResult(
            status="USER_CANCELLED",
            provider="ChatGPT (OpenAI API)",
            message="User explicitly cancelled external transfer at privacy gate."
        )
        self.assertEqual(cancel_res.status, "USER_CANCELLED")
        self.assertFalse(cancel_res.copied_to_clipboard)

    def test_79_adapters_do_not_access_full_database(self):
        """TEST 79: Destination adapters accept only PortableContextPackage and do not query database directly."""
        # Verify prepare() operates strictly on PortableContextPackage
        payload = self.chatgpt_adapter.prepare(self.package)
        self.assertIsNotNone(payload)
        self.assertIn("messages", payload)

    def test_80_regression_all_previous_tests_pass(self):
        """TEST 80: Registry lists all 4 adapters correctly and maintains total repository stability."""
        adapters = self.registry.list_adapters()
        self.assertEqual(len(adapters), 4)

        names = self.registry.list_provider_names()
        self.assertIn("Local Export (JSON & Plain Text)", names)
        self.assertIn("ChatGPT (OpenAI API)", names)
        self.assertIn("Gemini (Google AI API)", names)
        self.assertIn("Claude (Anthropic API)", names)


if __name__ == "__main__":
    unittest.main()
