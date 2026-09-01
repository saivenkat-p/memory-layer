"""
Milestone V6.5-E3: Offline LLM Memory Extractor Unit Tests.

Guarantees 100% offline testing without external LLM network calls using MockLLMClient.
Tests:
1. Valid JSON parsing and StructuredMemory object creation.
2. Malformed JSON response resilience.
3. Empty response handling.
4. Invalid memory type rejection.
5. Hallucinated message ID rejection.
6. Invalid/inverted index range rejection.
7. Candidate budget capping.
8. Missing required field rejection.
9. Provider failure / network exception handling.
10. Prompt formatting and message representation.
"""

import unittest
import json
import io
import socket
import urllib.error
from unittest.mock import patch, MagicMock
from app.models.schemas import Conversation, Message, StructuredMemory
from app.services.llm_memory_extractor import (
    BaseLLMClient,
    GeminiLLMClient,
    MockLLMClient,
    LLMMemoryExtractor,
    SYSTEM_EXTRACTION_PROMPT,
)


class TestLLMMemoryExtractorE3(unittest.TestCase):
    """Offline test suite for V6.5-E3 LLMMemoryExtractor."""

    def setUp(self):
        self.conv = Conversation(
            id="conv-test-101",
            title="Quantum Architecture and Study Schedule",
            source="ChatGPT",
            messages=[
                Message(id="msg-0", role="user", content="How should we configure portfolio optimization?", index=0),
                Message(id="msg-1", role="assistant", content="I suggest we adopt ARQPO with classical baselines.", index=1),
                Message(id="msg-2", role="user", content="Yes, approved! Let's use ARQPO for the project.", index=2),
                Message(id="msg-3", role="user", content="Also, I prefer dark mode UI for all dashboards.", index=3),
                Message(id="msg-4", role="user", content="Target is $500k seed funding.", index=4),
            ],
        )

    def test_01_valid_json_multi_memory_extraction(self):
        """TEST 01: Valid JSON response correctly parsed into validated StructuredMemory candidates."""
        mock_payload = json.dumps([
            {
                "memory_type": "decision",
                "content": "Adopted ARQPO with classical baselines for portfolio optimization.",
                "start_msg_index": 0,
                "end_msg_index": 2,
                "source_message_ids": ["msg-0", "msg-1", "msg-2"],
                "confidence": 1.0,
                "rationale": "Multi-turn decision adoption."
            },
            {
                "memory_type": "preference",
                "content": "User prefers dark mode UI for all dashboards.",
                "start_msg_index": 3,
                "end_msg_index": 3,
                "source_message_ids": ["msg-3"],
                "confidence": 1.0,
                "rationale": "Explicit user UI preference."
            },
            {
                "memory_type": "project_goal",
                "content": "Target $500k seed funding for the project.",
                "start_msg_index": 4,
                "end_msg_index": 4,
                "source_message_ids": ["msg-4"],
                "confidence": 1.0,
                "rationale": "Financial project target."
            }
        ])

        client = MockLLMClient(default_response=mock_payload)
        extractor = LLMMemoryExtractor(client=client)
        memories = extractor.extract_memories(self.conv)

        self.assertEqual(len(memories), 3)
        self.assertEqual(memories[0].memory_type, "decision")
        self.assertEqual(memories[0].start_msg_index, 0)
        self.assertEqual(memories[0].end_msg_index, 2)
        self.assertEqual(memories[0].source_message_ids, ["msg-0", "msg-1", "msg-2"])
        self.assertEqual(memories[1].memory_type, "preference")
        self.assertEqual(memories[2].memory_type, "project_goal")

    def test_02_malformed_json_graceful_recovery(self):
        """TEST 02: Malformed JSON output does not raise unhandled exception and returns empty list."""
        malformed_responses = [
            "This is not JSON at all.",
            '```json\n[{"memory_type": "decision", "content": ... truncated',
            "{unquoted_key: 123}",
        ]

        for resp in malformed_responses:
            client = MockLLMClient(default_response=resp)
            extractor = LLMMemoryExtractor(client=client)
            memories = extractor.extract_memories(self.conv)
            self.assertEqual(memories, [], "Malformed JSON must return empty list safely")

    def test_03_empty_response_handling(self):
        """TEST 03: Empty response or empty JSON array returns empty list."""
        for resp in ["[]", "", "   "]:
            client = MockLLMClient(default_response=resp)
            extractor = LLMMemoryExtractor(client=client)
            memories = extractor.extract_memories(self.conv)
            self.assertEqual(memories, [])

    def test_04_invalid_memory_type_rejected(self):
        """TEST 04: Candidates with invalid/unknown memory types are rejected."""
        mock_payload = json.dumps([
            {
                "memory_type": "speculative_opinion",  # Invalid type
                "content": "Speculative idea that should be rejected.",
                "start_msg_index": 0,
                "end_msg_index": 0,
                "source_message_ids": ["msg-0"],
            },
            {
                "memory_type": "decision",  # Valid type
                "content": "Valid decision memory.",
                "start_msg_index": 2,
                "end_msg_index": 2,
                "source_message_ids": ["msg-2"],
            }
        ])

        client = MockLLMClient(default_response=mock_payload)
        extractor = LLMMemoryExtractor(client=client)
        memories = extractor.extract_memories(self.conv)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].memory_type, "decision")

    def test_05_hallucinated_message_ids_rejected(self):
        """TEST 05: Candidates with hallucinated message IDs not present in conversation are rejected."""
        mock_payload = json.dumps([
            {
                "memory_type": "decision",
                "content": "Hallucinated message ID test.",
                "start_msg_index": 0,
                "end_msg_index": 0,
                "source_message_ids": ["msg-hallucinated-999"],
            }
        ])

        client = MockLLMClient(default_response=mock_payload)
        extractor = LLMMemoryExtractor(client=client)
        memories = extractor.extract_memories(self.conv)
        self.assertEqual(len(memories), 0, "Hallucinated message IDs must be rejected")

    def test_06_invalid_and_inverted_index_ranges_rejected(self):
        """TEST 06: Candidates with inverted (start > end) or out-of-bounds ranges are rejected."""
        mock_payload = json.dumps([
            {
                "memory_type": "decision",
                "content": "Inverted range.",
                "start_msg_index": 3,
                "end_msg_index": 1,  # Inverted
                "source_message_ids": ["msg-1", "msg-2", "msg-3"],
            },
            {
                "memory_type": "preference",
                "content": "Out of bounds range.",
                "start_msg_index": 0,
                "end_msg_index": 99,  # Out of bounds
                "source_message_ids": ["msg-0"],
            }
        ])

        client = MockLLMClient(default_response=mock_payload)
        extractor = LLMMemoryExtractor(client=client)
        memories = extractor.extract_memories(self.conv)
        self.assertEqual(len(memories), 0, "Invalid index ranges must be rejected")

    def test_07_candidate_budget_capping(self):
        """TEST 07: Candidate budget (max_candidates) is strictly enforced."""
        candidates = []
        for i in range(10):
            candidates.append({
                "memory_type": "fact",
                "content": f"Fact item {i}",
                "start_msg_index": 0,
                "end_msg_index": 0,
                "source_message_ids": ["msg-0"],
            })

        client = MockLLMClient(default_response=json.dumps(candidates))
        extractor = LLMMemoryExtractor(client=client, max_candidates=3)
        memories = extractor.extract_memories(self.conv)
        self.assertEqual(len(memories), 3, "Extractor must enforce candidate budget cap")

    def test_08_missing_required_fields_rejected(self):
        """TEST 08: Items missing content or index ranges are rejected."""
        mock_payload = json.dumps([
            {"memory_type": "decision"},  # Missing content and indices
            {"content": "Missing type and indices"},
            {"memory_type": "decision", "content": "Missing range"},
        ])

        client = MockLLMClient(default_response=mock_payload)
        extractor = LLMMemoryExtractor(client=client)
        memories = extractor.extract_memories(self.conv)
        self.assertEqual(len(memories), 0)

    def test_09_provider_failure_exception_handling(self):
        """TEST 09: When provider client raises an exception, extractor handles it gracefully."""
        class FailingClient(BaseLLMClient):
            def generate_json(self, system_instruction: str, user_prompt: str) -> str:
                raise RuntimeError("Simulated API rate limit / network error")

        extractor = LLMMemoryExtractor(client=FailingClient())
        memories = extractor.extract_memories(self.conv)
        self.assertEqual(memories, [], "Provider exceptions must be caught and logged safely")

    def test_10_prompt_formatting_and_message_representation(self):
        """TEST 10: Extractor correctly builds prompt containing turns, roles, and message IDs."""
        client = MockLLMClient(default_response="[]")
        extractor = LLMMemoryExtractor(client=client)
        prompt = extractor.build_prompt(self.conv)

        self.assertIn("Title: Quantum Architecture and Study Schedule", prompt)
        self.assertIn("[Turn 0] (user) ID: msg-0", prompt)
        self.assertIn("[Turn 2] (user) ID: msg-2", prompt)
        self.assertIn("How should we configure portfolio optimization?", prompt)

    def test_11_gemini_client_default_and_custom_timeout(self):
        """TEST 11: GeminiLLMClient defaults to 90s timeout and accepts custom timeout configuration."""
        client_default = GeminiLLMClient(api_key="test-key")
        self.assertEqual(client_default.timeout, 90)
        self.assertEqual(client_default.max_retries, 2)

        client_custom = GeminiLLMClient(api_key="test-key", timeout=120, max_retries=3)
        self.assertEqual(client_custom.timeout, 120)
        self.assertEqual(client_custom.max_retries, 3)

    @patch("urllib.request.urlopen")
    def test_12_gemini_client_retry_on_503_and_success(self, mock_urlopen):
        """TEST 12: Transient HTTP 503 triggers retry and succeeds on attempt 2."""
        # Setup mock: 1st call raises HTTPError 503, 2nd call succeeds
        err_503 = urllib.error.HTTPError(
            url="http://test",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"code": 503, "message": "High demand"}}')
        )
        
        success_response = MagicMock()
        success_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '[{"memory_type": "fact", "content": "Recovered fact"}]'}]}}],
            "usageMetadata": {"promptTokenCount": 150, "candidatesTokenCount": 40, "totalTokenCount": 190}
        }).encode("utf-8")
        success_response.__enter__.return_value = success_response
        success_response.__exit__.return_value = None

        mock_urlopen.side_effect = [err_503, success_response]

        client = GeminiLLMClient(api_key="test-key", timeout=90, max_retries=2, backoff_factor=0.01)
        res = client.generate_json("sys_inst", "user_prompt")

        self.assertIn("Recovered fact", res)
        self.assertEqual(client.last_metadata["attempts"], 2)
        self.assertEqual(client.last_metadata["retries"], 1)
        self.assertEqual(client.last_metadata["status_code"], 200)
        self.assertEqual(client.last_metadata["total_tokens"], 190)

    @patch("urllib.request.urlopen")
    def test_13_gemini_client_retry_on_timeout_and_success(self, mock_urlopen):
        """TEST 13: Socket timeout triggers retry and succeeds on attempt 2."""
        timeout_err = socket.timeout("The read operation timed out")
        
        success_response = MagicMock()
        success_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}],
            "usageMetadata": {"totalTokenCount": 80}
        }).encode("utf-8")
        success_response.__enter__.return_value = success_response
        success_response.__exit__.return_value = None

        mock_urlopen.side_effect = [timeout_err, success_response]

        client = GeminiLLMClient(api_key="test-key", timeout=90, max_retries=2, backoff_factor=0.01)
        res = client.generate_json("sys_inst", "user_prompt")

        self.assertEqual(res, "[]")
        self.assertEqual(client.last_metadata["attempts"], 2)
        self.assertEqual(client.last_metadata["retries"], 1)

    @patch("urllib.request.urlopen")
    def test_14_gemini_client_stop_after_max_retries(self, mock_urlopen):
        """TEST 14: Persistent transient error halts after max_retries (1 initial + 2 retries = 3 attempts)."""
        err_503 = urllib.error.HTTPError(
            url="http://test",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"code": 503, "message": "Persistent High Demand"}}')
        )
        mock_urlopen.side_effect = [err_503, err_503, err_503, err_503]

        client = GeminiLLMClient(api_key="test-key", timeout=90, max_retries=2, backoff_factor=0.01)
        with self.assertRaises(RuntimeError) as ctx:
            client.generate_json("sys_inst", "user_prompt")

        self.assertIn("Gemini API error (503)", str(ctx.exception))
        self.assertEqual(client.last_metadata["attempts"], 3)
        self.assertEqual(client.last_metadata["retries"], 2)
        self.assertEqual(client.last_metadata["status_code"], 503)

    @patch("urllib.request.urlopen")
    def test_15_gemini_client_no_retry_on_permanent_4xx(self, mock_urlopen):
        """TEST 15: Permanent 4xx HTTP error (e.g. 400 Bad Request or 404 Not Found) fails immediately without retrying."""
        err_404 = urllib.error.HTTPError(
            url="http://test",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"code": 404, "message": "Model not found"}}')
        )
        mock_urlopen.side_effect = err_404

        client = GeminiLLMClient(api_key="test-key", timeout=90, max_retries=2, backoff_factor=0.01)
        with self.assertRaises(RuntimeError) as ctx:
            client.generate_json("sys_inst", "user_prompt")

        self.assertIn("Gemini API error (404)", str(ctx.exception))
        self.assertEqual(client.last_metadata["attempts"], 1, "Must NOT retry on permanent 4xx")
        self.assertEqual(client.last_metadata["retries"], 0)
        self.assertEqual(client.last_metadata["status_code"], 404)

    @patch("urllib.request.urlopen")
    def test_16_gemini_client_token_metadata_recording(self, mock_urlopen):
        """TEST 16: Successful response populates token usage observability metadata."""
        success_response = MagicMock()
        success_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}],
            "usageMetadata": {
                "promptTokenCount": 210,
                "candidatesTokenCount": 55,
                "totalTokenCount": 265
            }
        }).encode("utf-8")
        success_response.__enter__.return_value = success_response
        success_response.__exit__.return_value = None

        mock_urlopen.return_value = success_response

        client = GeminiLLMClient(api_key="test-key")
        client.generate_json("sys_inst", "user_prompt")

        self.assertEqual(client.last_metadata["prompt_tokens"], 210)
        self.assertEqual(client.last_metadata["candidates_tokens"], 55)
        self.assertEqual(client.last_metadata["total_tokens"], 265)
        self.assertEqual(client.last_metadata["status_code"], 200)

    @patch("urllib.request.urlopen")
    def test_17_preflight_success(self, mock_urlopen):
        """TEST 17: Preflight succeeds when API is accessible, responsive, and model is gemini-3.7-flash."""
        success_response = MagicMock()
        success_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}]
        }).encode("utf-8")
        success_response.__enter__.return_value = success_response
        success_response.__exit__.return_value = None
        mock_urlopen.return_value = success_response

        client = GeminiLLMClient(api_key="test-key", model="gemini-3.7-flash")
        ok, msg = client.preflight_check()

        self.assertTrue(ok)
        self.assertIn("gemini-3.7-flash", msg)
        self.assertIn("passed", msg.lower())

    def test_18_preflight_missing_api_key(self):
        """TEST 18: Preflight fails immediately without network calls when GEMINI_API_KEY is missing."""
        with patch.dict("os.environ", {}, clear=True):
            client = GeminiLLMClient(api_key="", model="gemini-3.7-flash")
            ok, msg = client.preflight_check()

            self.assertFalse(ok)
            self.assertIn("GEMINI_API_KEY", msg)

    def test_19_preflight_wrong_model(self):
        """TEST 19: Preflight fails immediately when configured model is not gemini-3.7-flash."""
        client = GeminiLLMClient(api_key="test-key", model="gemini-2.5-flash")
        ok, msg = client.preflight_check()

        self.assertFalse(ok)
        self.assertIn("gemini-3.7-flash", msg)

    @patch("urllib.request.urlopen")
    def test_20_preflight_429_failure(self, mock_urlopen):
        """TEST 20: Preflight detects HTTP 429 quota exhaustion and reports failure without raising unhandled exception."""
        err_429 = urllib.error.HTTPError(
            url="http://test",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"code": 429, "message": "Quota exceeded"}}')
        )
        mock_urlopen.side_effect = err_429

        client = GeminiLLMClient(api_key="test-key", model="gemini-3.7-flash", max_retries=0)
        ok, msg = client.preflight_check()

        self.assertFalse(ok)
        self.assertIn("429", msg)

    @patch("urllib.request.urlopen")
    def test_21_preflight_503_failure(self, mock_urlopen):
        """TEST 21: Preflight detects HTTP 503 service unavailability / high demand and reports failure."""
        err_503 = urllib.error.HTTPError(
            url="http://test",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=io.BytesIO(b'{"error": {"code": 503, "message": "High demand"}}')
        )
        mock_urlopen.side_effect = err_503

        client = GeminiLLMClient(api_key="test-key", model="gemini-3.7-flash", max_retries=0)
        ok, msg = client.preflight_check()

        self.assertFalse(ok)
        self.assertIn("503", msg)


if __name__ == "__main__":
    unittest.main()
