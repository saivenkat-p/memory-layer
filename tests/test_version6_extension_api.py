"""
Milestone V6.0 Backend API Unit & Integration Test Suite.

Tests for `app/api/server.py` verifying:
1. Server startup & shutdown on background thread.
2. CORS security decision (restricts origins, no unrestricted wildcard '*').
3. /api/v1/health endpoint.
4. /api/v1/conversations endpoints.
5. /api/v1/search endpoint.
6. /api/v1/search/conversation endpoint (V3/V6 Feature 1).
7. /api/v1/context/compose endpoint (V4/V5A context composition).
8. /api/v1/context/handoff endpoint (V5B adapter handoff).
"""

import unittest
import json
import urllib.request
import urllib.error
import time

from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import Conversation, Message
from app.api.server import MemoryLayerAPIServer, DEFAULT_HOST, DEFAULT_PORT


class TestVersion6ExtensionAPI(unittest.TestCase):
    """Test suite for V6.0 Local REST API Server."""

    @classmethod
    def setUpClass(cls):
        # Initialize test data in repository
        cls.repo = ConversationRepository()
        cls.test_conv = Conversation(
            title="API Extension Test Conversation",
            source="ChatGPT",
            messages=[
                Message(role="user", content="How do we deploy the Memory Layer API server?", index=0),
                Message(role="assistant", content="We run python -m app.api.server on port 8000.", index=1)
            ]
        )
        cls.repo.save_conversation(cls.test_conv)

        # Launch API Server on test port 8001
        cls.port = 8001
        cls.server = MemoryLayerAPIServer(host=DEFAULT_HOST, port=cls.port)
        cls.server.start(daemon=True)
        time.sleep(1) # Give server time to bind

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.stop()

    def test_01_health_endpoint(self):
        """TEST 01: /api/v1/health returns status ok and version 6.0."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["version"], "6.0")

    def test_02_cors_security_headers(self):
        """TEST 02: CORS headers restrict origin to chrome-extension:// and local origins."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/health"
        ext_origin = "chrome-extension://abcdefghijklmnopqrstuvwxyz123456"
        req = urllib.request.Request(url, headers={"Origin": ext_origin}, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), ext_origin)

    def test_03_list_conversations(self):
        """TEST 03: GET /api/v1/conversations returns array of stored conversations."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("conversations", data)
            self.assertGreater(data["total"], 0)

    def test_04_get_single_conversation(self):
        """TEST 04: GET /api/v1/conversations/{id} returns full conversation with messages."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/{self.test_conv.id}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], self.test_conv.id)
            self.assertEqual(len(data["messages"]), 2)

    def test_05_global_search_endpoint(self):
        """TEST 05: POST /api/v1/search executes hybrid search."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/search"
        payload = json.dumps({"query": "deploy Memory Layer API server", "limit": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["query"], "deploy Memory Layer API server")
            self.assertIn("results", data)

    def test_06_in_conversation_search_endpoint(self):
        """TEST 06: POST /api/v1/search/conversation searches within a target conversation."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/search/conversation"
        payload = json.dumps({
            "conversation_id": self.test_conv.id,
            "query": "Memory Layer API server",
            "limit": 5
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["conversation_id"], self.test_conv.id)
            self.assertGreater(data["total"], 0)

    def test_07_context_composition_endpoint(self):
        """TEST 07: POST /api/v1/context/compose returns a PortableContextPackage."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/context/compose"
        payload = json.dumps({"query": "deploy API server", "max_candidates": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["schema_version"], "1.0")
            self.assertIn("context_text", data)
            self.assertIn("messages", data)

    def test_08_context_handoff_endpoint(self):
        """TEST 08: POST /api/v1/context/handoff executes local export destination adapter."""
        compose_url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/context/compose"
        c_payload = json.dumps({"query": "deploy API server", "max_candidates": 5}).encode("utf-8")
        c_req = urllib.request.Request(compose_url, data=c_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(c_req) as c_resp:
            pkg_data = json.loads(c_resp.read().decode("utf-8"))

        handoff_url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/context/handoff"
        h_payload = json.dumps({
            "package": pkg_data,
            "destination": "Local Export (JSON & Plain Text)",
            "config": {}
        }).encode("utf-8")
        h_req = urllib.request.Request(handoff_url, data=h_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(h_req) as h_resp:
            self.assertEqual(h_resp.status, 200)
            res_data = json.loads(h_resp.read().decode("utf-8"))
            self.assertEqual(res_data["status"], "SUCCESS")

    def test_09_gemini_provider_search_response(self):
        """TEST 09 (V6.2): Save Gemini-originated conversation and verify search returns Gemini source for browser extension."""
        gemini_conv = Conversation(
            title="Gemini Architecture Strategy",
            source="Gemini",
            messages=[
                Message(role="user", content="How do we structure Gemini extension adapter?", index=0),
                Message(role="assistant", content="We create GeminiAdapter extending BaseProviderAdapter for gemini.google.com.", index=1)
            ]
        )
        self.repo.save_conversation(gemini_conv)

        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/search"
        payload = json.dumps({"query": "Gemini extension adapter", "limit": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            self.assertGreater(len(results), 0)
            matched_sources = [r["source"] for r in results if "Gemini" in r["conversation_title"]]
            self.assertIn("Gemini", matched_sources)

    def test_10_bidirectional_cross_ai_search(self):
        """TEST 10 (V6.2): Verify bidirectional cross-AI retrieval (Gemini finding ChatGPT memory & ChatGPT finding Gemini memory)."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/search"
        
        # 1. Search for ChatGPT memory (as if inside Gemini overlay)
        payload1 = json.dumps({"query": "deploy the Memory Layer API server", "limit": 5}).encode("utf-8")
        req1 = urllib.request.Request(url, data=payload1, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req1) as resp1:
            data1 = json.loads(resp1.read().decode("utf-8"))
            sources1 = [r["source"] for r in data1.get("results", [])]
            self.assertIn("ChatGPT", sources1)

        # 2. Search for Gemini memory (as if inside ChatGPT overlay)
        payload2 = json.dumps({"query": "Gemini Architecture Strategy", "limit": 5}).encode("utf-8")
        req2 = urllib.request.Request(url, data=payload2, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req2) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))
            sources2 = [r["source"] for r in data2.get("results", [])]
            self.assertIn("Gemini", sources2)

    def test_11_sync_valid_chatgpt_payload(self):
        """TEST 11 (V6.2.x): POST /api/v1/conversations/sync ingests valid ChatGPT conversation payload."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload = json.dumps({
            "provider": "ChatGPT",
            "conversation_id": "chatgpt-test-sync-101",
            "title": "Quantum Algorithm Research Notes",
            "messages": [
                {"role": "user", "content": "Explain Grover search algorithm complexity.", "index": 0},
                {"role": "assistant", "content": "Grover search algorithm achieves O(sqrt(N)) quadratic speedup.", "index": 1}
            ]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["conversation_id"], "chatgpt-test-sync-101")
            self.assertEqual(data["messages_synced"], 2)

    def test_12_sync_valid_gemini_payload(self):
        """TEST 12 (V6.2.x): POST /api/v1/conversations/sync ingests valid Gemini conversation payload."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload = json.dumps({
            "provider": "Gemini",
            "conversation_id": "gemini-test-sync-202",
            "title": "Autonomous Agent Design",
            "messages": [
                {"role": "user", "content": "What is the primary role of Google Antigravity SDK?", "index": 0},
                {"role": "assistant", "content": "Antigravity SDK orchestrates autonomous AI agents with tools and memory.", "index": 1}
            ]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["conversation_id"], "gemini-test-sync-202")
            self.assertEqual(data["messages_synced"], 2)

    def test_13_sync_invalid_provider_rejected(self):
        """TEST 13 (V6.2.x): Sync endpoint rejects invalid/unsupported provider with 400."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload = json.dumps({
            "provider": "UnsupportedAI",
            "conversation_id": "bad-provider-1",
            "title": "Bad Provider Chat",
            "messages": [{"role": "user", "content": "Hello", "index": 0}]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTPError 400 for invalid provider")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            body = json.loads(e.read().decode("utf-8"))
            self.assertEqual(body["error_code"], "INVALID_PROVIDER")

    def test_14_sync_invalid_payload_rejected(self):
        """TEST 14 (V6.2.x): Sync endpoint rejects missing fields or empty messages array with 400."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload = json.dumps({
            "provider": "ChatGPT",
            "conversation_id": "empty-msg-1",
            "title": "Empty Messages Chat",
            "messages": []
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTPError 400 for empty messages payload")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            body = json.loads(e.read().decode("utf-8"))
            self.assertEqual(body["error_code"], "INVALID_INPUT")

    def test_15_sync_idempotency_no_duplicates(self):
        """TEST 15 (V6.2.x): Repeated identical sync calls do NOT create duplicate conversation or message records."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload_bytes = json.dumps({
            "provider": "ChatGPT",
            "conversation_id": "idempotency-check-999",
            "title": "Idempotent Sync Test",
            "messages": [
                {"role": "user", "content": "First prompt message", "index": 0},
                {"role": "assistant", "content": "First response message", "index": 1}
            ]
        }).encode("utf-8")

        # First sync
        req1 = urllib.request.Request(url, data=payload_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req1) as resp1:
            self.assertEqual(resp1.status, 200)

        initial_count = len(self.repo.list_conversations())

        # Second identical sync
        req2 = urllib.request.Request(url, data=payload_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req2) as resp2:
            self.assertEqual(resp2.status, 200)

        after_second_count = len(self.repo.list_conversations())
        self.assertEqual(initial_count, after_second_count)

        fetched = self.repo.get_conversation("idempotency-check-999")
        self.assertEqual(fetched.message_count, 2)

    def test_16_sync_incremental_message_addition(self):
        """TEST 16 (V6.2.x): Syncing a conversation with an added turn updates the record seamlessly."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/conversations/sync"
        payload_bytes = json.dumps({
            "provider": "ChatGPT",
            "conversation_id": "idempotency-check-999",
            "title": "Idempotent Sync Test",
            "messages": [
                {"role": "user", "content": "First prompt message", "index": 0},
                {"role": "assistant", "content": "First response message", "index": 1},
                {"role": "user", "content": "Follow-up question about Grover", "index": 2},
                {"role": "assistant", "content": "Follow-up response about Grover speedup", "index": 3}
            ]
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        fetched = self.repo.get_conversation("idempotency-check-999")
        self.assertEqual(fetched.message_count, 4)

    def test_17_search_finds_newly_synced_content(self):
        """TEST 17 (V6.2.x): Hybrid search immediately retrieves newly synced conversation content."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/search"
        payload = json.dumps({"query": "Grover search algorithm quadratic speedup", "limit": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            self.assertGreater(len(results), 0)
            matched_titles = [r["conversation_title"] for r in results]
            self.assertIn("Quantum Algorithm Research Notes", matched_titles)


if __name__ == "__main__":
    unittest.main()


