"""
Isolated Opt-In Live API Integration Tests for ChatGPT (OpenAI API).

MANDATORY DIRECTIVE:
This file is NOT executed during standard `python -m unittest discover tests`.
To run live API tests against real OpenAI endpoints, set the environment variable:
  RUN_LIVE_API_TESTS=1
  OPENAI_API_KEY=sk-...
"""

import os
import unittest

from app.models.schemas import PortableContextPackage
from app.services.destination_adapters.chatgpt import ChatGPTAdapter

RUN_LIVE = os.environ.get("RUN_LIVE_API_TESTS") == "1"


@unittest.skipUnless(RUN_LIVE, "Skipping live API tests. Set RUN_LIVE_API_TESTS=1 and OPENAI_API_KEY to execute.")
class TestLiveChatGPTAPI(unittest.TestCase):
    """Opt-in live integration test suite for real OpenAI API endpoints."""

    def setUp(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            self.skipTest("OPENAI_API_KEY environment variable not set.")

        self.adapter = ChatGPTAdapter()  # No mock executor -> real HTTP
        self.package = PortableContextPackage(
            package_id="live-test-001",
            title="Live Context Test",
            topic="Test Memory Layer Integration",
            context_text="# Context from Memory Layer\n\n[User]\nHello from Memory Layer live test.",
            source_conversations=[{"id": "conv-1", "title": "Live Test", "source": "ChatGPT"}],
            source_providers={"ChatGPT": 1},
            messages=[
                {
                    "order": 1,
                    "message_id": "msg-1",
                    "conversation_id": "conv-1",
                    "conversation_title": "Live Test",
                    "provider": "ChatGPT",
                    "role": "user",
                    "content": "Reply with 'MEMORY_LAYER_LIVE_TEST_SUCCESS' if you read this historical context.",
                    "message_index": 0
                }
            ],
            provenance=[{"order": 1, "message_id": "msg-1"}]
        )

    def test_live_chatgpt_api_execution(self):
        """Live test sending real HTTP POST to OpenAI Chat API."""
        result = self.adapter.execute(self.package, config={"api_key": self.api_key})

        self.assertEqual(result.status, "API_RESPONSE")
        self.assertIsNotNone(result.response_payload)
        self.assertIn("response_text", result.response_payload)
        print("\n[LIVE API RESPONSE]:", result.response_payload["response_text"])


if __name__ == "__main__":
    unittest.main()
