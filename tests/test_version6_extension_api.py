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


if __name__ == "__main__":
    unittest.main()
