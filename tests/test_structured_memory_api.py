"""
Milestone V6.5-E4: Structured Memory Retrieval & REST API Test Suite.

Comprehensive tests verifying:
1. StructuredMemorySearchEngine:
   - Filtering by memory_type (decision, preference, fact, project_goal)
   - Filtering by conversation_id
   - Filtering by status (active, superseded, all)
   - Pagination (limit, offset, total_count)
   - Search by query keywords and semantics with relevance threshold
   - Provenance hydration (resolving exact source messages)
2. Local REST API Endpoints:
   - GET /api/v1/memories (list, filters, pagination, hydration)
   - GET /api/v1/memories/{id} (single item, provenance resolution, 404 handling)
   - POST /api/v1/memories/search (hybrid query, threshold, type filter, invalid parameters)
   - DELETE /api/v1/memories/{id} (deletion, 404 handling)
   - CORS headers (verifying DELETE is in allowed methods)
"""

import unittest
import json
import os
import urllib.request
import urllib.error
import time

from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.structured_memory_repository import StructuredMemoryRepository
from app.search.structured_memory_search import StructuredMemorySearchEngine, StructuredMemorySearchResult
from app.models.schemas import Conversation, Message, StructuredMemory
from app.api.server import MemoryLayerAPIServer, MemoryLayerHTTPRequestHandler, DEFAULT_HOST


class TestStructuredMemoryRetrievalAndAPI(unittest.TestCase):
    """Test suite for Milestone V6.5-E4."""

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join("data", "test_v65_e4_api.db")
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

        cls.db = Database(cls.test_db_path)
        cls.conv_repo = ConversationRepository(cls.db)
        cls.memory_repo = StructuredMemoryRepository(cls.db)
        cls.search_engine = StructuredMemorySearchEngine(
            memory_repo=cls.memory_repo,
            conv_repo=cls.conv_repo,
            db=cls.db
        )

        # Seed Test Conversation 1
        cls.conv1 = Conversation(
            id="conv-e4-quantum",
            title="Quantum Portfolio Architecture",
            source="ChatGPT",
            messages=[
                Message(id="msg-e4-0", role="user", content="What solver architecture should we adopt for WISER?", index=0),
                Message(id="msg-e4-1", role="assistant", content="I propose we adopt ARQPO with PCA-QAOA.", index=1),
                Message(id="msg-e4-2", role="user", content="Approved! Let's adopt ARQPO as our primary optimization framework.", index=2),
                Message(id="msg-e4-3", role="user", content="I prefer Qiskit over Cirq for quantum circuit simulation.", index=3),
            ]
        )
        cls.conv_repo.save_conversation(cls.conv1)

        # Seed Test Conversation 2
        cls.conv2 = Conversation(
            id="conv-e4-learning",
            title="Python and DSA Study Plan",
            source="Gemini",
            messages=[
                Message(id="msg-e4-10", role="user", content="My goal is to master Python fundamentals and DSA within 6 months.", index=0),
                Message(id="msg-e4-11", role="assistant", content="Here is a structured 6-month roadmap.", index=1),
                Message(id="msg-e4-12", role="user", content="Remember that binary search requires a sorted array.", index=2),
            ]
        )
        cls.conv_repo.save_conversation(cls.conv2)

        # Seed Structured Memories
        cls.mem_decision = StructuredMemory(
            id="mem-e4-decision-1",
            conversation_id=cls.conv1.id,
            memory_type="decision",
            content="Adopted ARQPO framework for portfolio optimization.",
            start_msg_index=1,
            end_msg_index=2,
            source_message_ids=["msg-e4-1", "msg-e4-2"],
            provider="ChatGPT",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_decision)

        cls.mem_pref = StructuredMemory(
            id="mem-e4-pref-1",
            conversation_id=cls.conv1.id,
            memory_type="preference",
            content="User prefers Qiskit for quantum circuit simulation.",
            start_msg_index=3,
            end_msg_index=3,
            source_message_ids=["msg-e4-3"],
            provider="ChatGPT",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_pref)

        cls.mem_goal = StructuredMemory(
            id="mem-e4-goal-1",
            conversation_id=cls.conv2.id,
            memory_type="project_goal",
            content="Master Python fundamentals and DSA within 6 months.",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-e4-10"],
            provider="Gemini",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_goal)

        cls.mem_fact = StructuredMemory(
            id="mem-e4-fact-1",
            conversation_id=cls.conv2.id,
            memory_type="fact",
            content="Binary search algorithm strictly requires a sorted array.",
            start_msg_index=2,
            end_msg_index=2,
            source_message_ids=["msg-e4-12"],
            provider="Gemini",
            status="superseded"
        )
        cls.memory_repo.save_memory(cls.mem_fact)

        # Save original handler singletons and point to test repository for isolated API tests
        cls._orig_repo = MemoryLayerHTTPRequestHandler.repo
        cls._orig_memory_repo = MemoryLayerHTTPRequestHandler.memory_repo
        cls._orig_search_engine = MemoryLayerHTTPRequestHandler.memory_search_engine
        cls._orig_hybrid = MemoryLayerHTTPRequestHandler.hybrid_engine
        cls._orig_find_here = MemoryLayerHTTPRequestHandler.find_here_engine
        cls._orig_composer = MemoryLayerHTTPRequestHandler.composer

        MemoryLayerHTTPRequestHandler.repo = cls.conv_repo
        MemoryLayerHTTPRequestHandler.memory_repo = cls.memory_repo
        MemoryLayerHTTPRequestHandler.memory_search_engine = cls.search_engine

        # Start test server on port 8002
        cls.port = 8002
        cls.server = MemoryLayerAPIServer(host=DEFAULT_HOST, port=cls.port)
        cls.server.start(daemon=True)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.stop()
        # Restore original handler singletons
        MemoryLayerHTTPRequestHandler.repo = cls._orig_repo
        MemoryLayerHTTPRequestHandler.memory_repo = cls._orig_memory_repo
        MemoryLayerHTTPRequestHandler.memory_search_engine = cls._orig_search_engine
        MemoryLayerHTTPRequestHandler.hybrid_engine = cls._orig_hybrid
        MemoryLayerHTTPRequestHandler.find_here_engine = cls._orig_find_here
        MemoryLayerHTTPRequestHandler.composer = cls._orig_composer

        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    # =========================================================================
    # SEARCH ENGINE UNIT TESTS
    # =========================================================================

    def test_01_search_engine_list_all_and_pagination(self):
        """TEST 01: Engine lists memories with pagination and total count."""
        memories, total = self.search_engine.list_memories(status="all", limit=2, offset=0)
        self.assertEqual(total, 4)
        self.assertEqual(len(memories), 2)

    def test_02_search_engine_filter_by_type(self):
        """TEST 02: Engine filters memories by memory_type."""
        decisions, count = self.search_engine.list_memories(memory_type="decision", status="all")
        self.assertEqual(count, 1)
        self.assertEqual(decisions[0]["id"], "mem-e4-decision-1")
        self.assertEqual(decisions[0]["memory_type"], "decision")

    def test_03_search_engine_filter_by_conversation(self):
        """TEST 03: Engine filters memories by conversation_id."""
        conv2_mems, count = self.search_engine.list_memories(conversation_id="conv-e4-learning", status="all")
        self.assertEqual(count, 2)
        for m in conv2_mems:
            self.assertEqual(m["conversation_id"], "conv-e4-learning")

    def test_04_search_engine_filter_by_status(self):
        """TEST 04: Engine filters active vs superseded memories."""
        active_mems, count = self.search_engine.list_memories(status="active")
        self.assertEqual(count, 3)
        superseded_mems, count_sup = self.search_engine.list_memories(status="superseded")
        self.assertEqual(count_sup, 1)
        self.assertEqual(superseded_mems[0]["id"], "mem-e4-fact-1")

    def test_05_search_engine_get_memory_provenance_hydration(self):
        """TEST 05: Engine resolves exact source messages upon provenance hydration."""
        hydrated = self.search_engine.get_memory_with_provenance("mem-e4-decision-1", hydrate_provenance=True)
        self.assertIsNotNone(hydrated)
        self.assertIn("source_messages", hydrated)
        self.assertEqual(len(hydrated["source_messages"]), 2)
        self.assertEqual(hydrated["source_messages"][0]["id"], "msg-e4-1")
        self.assertEqual(hydrated["source_messages"][1]["id"], "msg-e4-2")

    def test_06_search_engine_keyword_and_relevance_search(self):
        """TEST 06: Engine finds relevant memories by query and returns scores above threshold."""
        results = self.search_engine.search_memories("Qiskit simulation preference", threshold=0.35)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top.memory.id, "mem-e4-pref-1")
        self.assertGreaterEqual(top.score, 0.35)
        self.assertEqual(len(top.source_messages), 1)
        self.assertEqual(top.source_messages[0].id, "msg-e4-3")

    def test_07_search_engine_type_filtered_search(self):
        """TEST 07: Search respects memory_type filter."""
        results = self.search_engine.search_memories("Python DSA", memory_type="project_goal")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].memory.memory_type, "project_goal")
        self.assertEqual(results[0].memory.id, "mem-e4-goal-1")

    # =========================================================================
    # REST API INTEGRATION TESTS
    # =========================================================================

    def test_08_api_get_memories_list(self):
        """TEST 08: GET /api/v1/memories returns memories list and total."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("memories", data)
            self.assertIn("total", data)
            self.assertEqual(data["total"], 3)  # default status='active'

    def test_09_api_get_memories_filter_type(self):
        """TEST 09: GET /api/v1/memories?type=decision filters by type."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=decision"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["memories"][0]["memory_type"], "decision")

    def test_10_api_get_memories_invalid_type_400(self):
        """TEST 10: GET /api/v1/memories?type=invalid returns HTTP 400."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=invalid_type"
        req = urllib.request.Request(url, method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_11_api_get_memories_hydrated(self):
        """TEST 11: GET /api/v1/memories?hydrate=true includes source_messages."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=preference&hydrate=true"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(len(data["memories"]), 1)
            self.assertIn("source_messages", data["memories"][0])
            self.assertEqual(len(data["memories"][0]["source_messages"]), 1)

    def test_12_api_get_single_memory_by_id(self):
        """TEST 12: GET /api/v1/memories/{id} returns single memory with provenance."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/mem-e4-decision-1"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], "mem-e4-decision-1")
            self.assertEqual(data["memory_type"], "decision")
            self.assertEqual(len(data["source_messages"]), 2)

    def test_13_api_get_single_memory_404(self):
        """TEST 13: GET /api/v1/memories/{id} returns 404 for unknown ID."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/non-existent-memory-id"
        req = urllib.request.Request(url, method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

    def test_14_api_post_memories_search(self):
        """TEST 14: POST /api/v1/memories/search executes hybrid search."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/search"
        payload = json.dumps({
            "query": "ARQPO framework optimization",
            "threshold": 0.30,
            "hydrate": True
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["query"], "ARQPO framework optimization")
            self.assertGreater(data["total"], 0)
            top = data["results"][0]
            self.assertEqual(top["memory"]["id"], "mem-e4-decision-1")
            self.assertIn("source_messages", top)
            self.assertEqual(len(top["source_messages"]), 2)

    def test_15_api_post_memories_search_empty_query(self):
        """TEST 15: POST /api/v1/memories/search with empty query returns empty results."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/search"
        payload = json.dumps({"query": ""}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 0)
            self.assertEqual(len(data["results"]), 0)

    def test_16_api_post_memories_search_invalid_type_400(self):
        """TEST 16: POST /api/v1/memories/search with invalid type returns 400."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/search"
        payload = json.dumps({
            "query": "quantum",
            "type": "invalid_type"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_17_api_delete_memory(self):
        """TEST 17: DELETE /api/v1/memories/{id} deletes memory."""
        # Create temporary memory to delete
        temp_mem = StructuredMemory(
            id="mem-to-delete",
            conversation_id=self.conv1.id,
            memory_type="preference",
            content="Temporary preference to delete.",
            start_msg_index=3,
            end_msg_index=3,
            source_message_ids=["msg-e4-3"],
            provider="ChatGPT"
        )
        self.memory_repo.save_memory(temp_mem)

        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/mem-to-delete"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["deleted_id"], "mem-to-delete")

        # Verify deletion
        self.assertIsNone(self.memory_repo.get_memory("mem-to-delete"))

    def test_18_api_delete_memory_404(self):
        """TEST 18: DELETE /api/v1/memories/{id} returns 404 for non-existent memory."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/already-deleted-memory"
        req = urllib.request.Request(url, method="DELETE")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

    def test_19_api_cors_allowed_methods_includes_delete(self):
        """TEST 19: OPTIONS request includes DELETE in Access-Control-Allow-Methods."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories"
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            methods = resp.headers.get("Access-Control-Allow-Methods", "")
            self.assertIn("DELETE", methods)


if __name__ == "__main__":
    unittest.main()
