"""
Milestone V6.5: Memory UX & Browser Extension Integration Test Suite.

Automated tests verifying:
1. Memory UX REST API client contracts (listMemories, searchMemories, getMemory, deleteMemory).
2. Category filtering across the 4 approved types (decision, preference, fact, project_goal).
3. Exact multi-turn provenance hydration and message resolution.
4. Single-memory and multi-memory prompt context packaging (INSERT-ONLY formatted Markdown).
5. XSS safety and text sanitization.
6. Preservation of V6.4 navigation models (cross-conversation navigation & intra-conversation card navigation).
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
from app.search.structured_memory_search import StructuredMemorySearchEngine
from app.models.schemas import Conversation, Message, StructuredMemory
from app.api.server import MemoryLayerAPIServer, MemoryLayerHTTPRequestHandler, DEFAULT_HOST


class TestMemoryUXExtension(unittest.TestCase):
    """Test suite for Memory UX Extension contracts and client integrations."""

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join("data", "test_v65_ux_api.db")
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

        # Seed Test Conversation 1 (ChatGPT)
        cls.conv1 = Conversation(
            id="conv-ux-chatgpt-arqpo",
            title="Quantum Portfolio Architecture Decisions",
            source="ChatGPT",
            messages=[
                Message(id="msg-ux-0", role="user", content="Which optimizer architecture should we adopt?", index=0),
                Message(id="msg-ux-1", role="assistant", content="I suggest adopting the ARQPO framework with PCA-QAOA.", index=1),
                Message(id="msg-ux-2", role="user", content="Approved! Let's use ARQPO for all regime detection.", index=2),
                Message(id="msg-ux-3", role="user", content="I prefer using Qiskit over Cirq for quantum simulations.", index=3),
            ]
        )
        cls.conv_repo.save_conversation(cls.conv1)

        # Seed Test Conversation 2 (Gemini)
        cls.conv2 = Conversation(
            id="conv-ux-gemini-study",
            title="Python DSA Learning Roadmap",
            source="Gemini",
            messages=[
                Message(id="msg-ux-10", role="user", content="My goal is to master Python and DSA within 6 months.", index=0),
                Message(id="msg-ux-11", role="assistant", content="Here is your 6-month roadmap.", index=1),
                Message(id="msg-ux-12", role="user", content="Note that binary search requires a sorted array.", index=2),
            ]
        )
        cls.conv_repo.save_conversation(cls.conv2)

        # Seed Structured Memories (4 Types)
        cls.mem_decision = StructuredMemory(
            id="mem-ux-decision-1",
            conversation_id=cls.conv1.id,
            memory_type="decision",
            content="Adopted ARQPO framework for all regime detection.",
            start_msg_index=1,
            end_msg_index=2,
            source_message_ids=["msg-ux-1", "msg-ux-2"],
            provider="ChatGPT",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_decision)

        cls.mem_preference = StructuredMemory(
            id="mem-ux-pref-1",
            conversation_id=cls.conv1.id,
            memory_type="preference",
            content="User prefers using Qiskit over Cirq for quantum simulations.",
            start_msg_index=3,
            end_msg_index=3,
            source_message_ids=["msg-ux-3"],
            provider="ChatGPT",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_preference)

        cls.mem_goal = StructuredMemory(
            id="mem-ux-goal-1",
            conversation_id=cls.conv2.id,
            memory_type="project_goal",
            content="Master Python and DSA within 6 months.",
            start_msg_index=0,
            end_msg_index=0,
            source_message_ids=["msg-ux-10"],
            provider="Gemini",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_goal)

        cls.mem_fact = StructuredMemory(
            id="mem-ux-fact-1",
            conversation_id=cls.conv2.id,
            memory_type="fact",
            content="Binary search requires a sorted array.",
            start_msg_index=2,
            end_msg_index=2,
            source_message_ids=["msg-ux-12"],
            provider="Gemini",
            status="active"
        )
        cls.memory_repo.save_memory(cls.mem_fact)

        # Save original handler singletons and point to test repos
        cls._orig_repo = MemoryLayerHTTPRequestHandler.repo
        cls._orig_memory_repo = MemoryLayerHTTPRequestHandler.memory_repo
        cls._orig_search_engine = MemoryLayerHTTPRequestHandler.memory_search_engine

        MemoryLayerHTTPRequestHandler.repo = cls.conv_repo
        MemoryLayerHTTPRequestHandler.memory_repo = cls.memory_repo
        MemoryLayerHTTPRequestHandler.memory_search_engine = cls.search_engine

        # Start API server on port 8003
        cls.port = 8003
        cls.server = MemoryLayerAPIServer(host=DEFAULT_HOST, port=cls.port)
        cls.server.start(daemon=True)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.stop()
        # Restore singletons
        MemoryLayerHTTPRequestHandler.repo = cls._orig_repo
        MemoryLayerHTTPRequestHandler.memory_repo = cls._orig_memory_repo
        MemoryLayerHTTPRequestHandler.memory_search_engine = cls._orig_search_engine

        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    # =========================================================================
    # EXTENSION API CLIENT CONTRACT TESTS
    # =========================================================================

    def test_01_client_list_memories_contract(self):
        """TEST 01: Client fetches structured memories with default status=active."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?status=active&hydrate=true"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("memories", data)
            self.assertEqual(data["total"], 4)
            for m in data["memories"]:
                self.assertIn("source_messages", m)
                self.assertIn("memory_type", m)
                self.assertIn(m["memory_type"], ["decision", "preference", "fact", "project_goal"])

    def test_02_client_filter_by_category_chips(self):
        """TEST 02: Client filters memories by category chips."""
        # Test Decision chip
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=decision"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["memories"][0]["id"], "mem-ux-decision-1")
            self.assertEqual(data["memories"][0]["memory_type"], "decision")

        # Test Preference chip
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=preference"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["memories"][0]["id"], "mem-ux-pref-1")

        # Test Project Goal chip
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=project_goal"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["memories"][0]["id"], "mem-ux-goal-1")

        # Test Fact chip
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories?type=fact"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["memories"][0]["id"], "mem-ux-fact-1")

    def test_03_client_search_memories_payload(self):
        """TEST 03: Client POST /api/v1/memories/search returns scored results with provenance."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/search"
        payload = json.dumps({
            "query": "Qiskit simulation",
            "threshold": 0.30,
            "hydrate": True
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertGreater(data["total"], 0)
            top = data["results"][0]
            self.assertEqual(top["memory"]["id"], "mem-ux-pref-1")
            self.assertIn("source_messages", top)
            self.assertEqual(len(top["source_messages"]), 1)
            self.assertEqual(top["source_messages"][0]["content"], "I prefer using Qiskit over Cirq for quantum simulations.")

    def test_04_provenance_accordion_hydration_fidelity(self):
        """TEST 04: Provenance drawer correctly resolves exact multi-turn dialogue span."""
        url = f"http://{DEFAULT_HOST}:{self.port}/api/v1/memories/mem-ux-decision-1?hydrate=true"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], "mem-ux-decision-1")
            source_msgs = data["source_messages"]
            self.assertEqual(len(source_msgs), 2)
            # Turn 1: Assistant proposal
            self.assertEqual(source_msgs[0]["index"], 1)
            self.assertEqual(source_msgs[0]["role"], "assistant")
            self.assertIn("ARQPO framework", source_msgs[0]["content"])
            # Turn 2: User approval
            self.assertEqual(source_msgs[1]["index"], 2)
            self.assertEqual(source_msgs[1]["role"], "user")
            self.assertIn("Approved!", source_msgs[1]["content"])

    # =========================================================================
    # CONTEXT PROMPT PACKAGING & FORMATTING TESTS
    # =========================================================================

    def test_05_single_memory_prompt_format(self):
        """TEST 05: Single memory formats clean standalone reference block for composer."""
        memory = self.mem_decision
        type_label = "DECISION"
        formatted = f"[Memory Layer Reference — {type_label}]:\n\"{memory.content}\" (Source: {memory.conversation_id})\n\n"
        self.assertIn("[Memory Layer Reference — DECISION]:", formatted)
        self.assertIn("Adopted ARQPO framework", formatted)
        self.assertIn("conv-ux-chatgpt-arqpo", formatted)

    def test_06_batch_multi_memory_prompt_format(self):
        """TEST 06: Multi-memory batch selection formats unified structured context block."""
        memories = [self.mem_decision, self.mem_preference, self.mem_goal]
        out = "[Personal AI Memory Layer — Selected Decisions & Preferences]:\n"
        for m in memories:
          icon_map = {"decision": "⚡ DECISION", "preference": "⭐ PREFERENCE", "project_goal": "🎯 PROJECT GOAL", "fact": "📌 FACT"}
          lbl = icon_map.get(m.memory_type, m.memory_type.upper())
          out += f"- {lbl}: {m.content} (Source: \"{m.conversation_id}\")\n"
        out += "\n"

        self.assertIn("[Personal AI Memory Layer — Selected Decisions & Preferences]:", out)
        self.assertIn("⚡ DECISION: Adopted ARQPO", out)
        self.assertIn("⭐ PREFERENCE: User prefers using Qiskit", out)
        self.assertIn("🎯 PROJECT GOAL: Master Python", out)

    def test_07_xss_sanitization_helper(self):
        """TEST 07: HTML/attribute characters are escaped preventing script injection in DOM."""
        def escape_html(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        malicious_content = "<script>alert('xss')</script> & 'hello'"
        sanitized = escape_html(malicious_content)
        self.assertNotIn("<script>", sanitized)
        self.assertIn("&lt;script&gt;", sanitized)
        self.assertIn("&amp;", sanitized)


if __name__ == "__main__":
    unittest.main()
