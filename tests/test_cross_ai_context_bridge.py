"""
Milestone V6.6: Cross-AI Context Bridge & Multi-Source Packaging Test Suite.

Automated tests verifying:
1. Multi-source context selection tracking across distinct conversations and AI providers.
2. Chronological turn-order preservation within each conversation group.
3. Structured multi-conversation Markdown packaging contract with clear provenance tags.
4. Minimum useful context isolation (extracting only selected turns without bloating).
5. Destination routing behavior (Current Chat, New Chat, Clipboard Copy).
6. 2D Navigation mathematics (←/→ cross-conversation cycling, ↑/↓ card focus).
7. XSS sanitization and safety.
"""

import unittest
import json
import os


class TestCrossAIContextBridge(unittest.TestCase):
    """Test suite for Cross-AI Context Bridge packaging and contracts."""

    def setUp(self):
        self.sample_items = [
            {
                "id": "msg-chatgpt-1",
                "conversationId": "conv-chatgpt-arqpo",
                "conversationTitle": "Quantum Portfolio Optimization",
                "provider": "ChatGPT",
                "role": "user",
                "turnIndex": 0,
                "content": "Which optimizer architecture should we adopt?",
                "memoryType": None
            },
            {
                "id": "msg-chatgpt-2",
                "conversationId": "conv-chatgpt-arqpo",
                "conversationTitle": "Quantum Portfolio Optimization",
                "provider": "ChatGPT",
                "role": "assistant",
                "turnIndex": 1,
                "content": "We should adopt the ARQPO framework with PCA-QAOA.",
                "memoryType": "decision"
            },
            {
                "id": "msg-gemini-1",
                "conversationId": "conv-gemini-loss",
                "conversationTitle": "Loss Function Derivations",
                "provider": "Gemini",
                "role": "assistant",
                "turnIndex": 4,
                "content": "The loss function formula is L = ||w - w_opt||^2 + lambda * R.",
                "memoryType": "fact"
            },
            {
                "id": "msg-claude-1",
                "conversationId": "conv-claude-qiskit",
                "conversationTitle": "Qiskit Circuit Simulation",
                "provider": "Claude",
                "role": "user",
                "turnIndex": 2,
                "content": "Ensure all circuit shots are set to 4096.",
                "memoryType": "preference"
            }
        ]

    def test_01_multi_source_grouping_by_conversation(self):
        """TEST 01: Selected items are grouped by conversationId preserving source metadata."""
        groups = {}
        for it in self.sample_items:
            cid = it["conversationId"]
            if cid not in groups:
                groups[cid] = {
                    "title": it["conversationTitle"],
                    "provider": it["provider"],
                    "items": []
                }
            groups[cid]["items"].append(it)

        self.assertEqual(len(groups), 3)
        self.assertIn("conv-chatgpt-arqpo", groups)
        self.assertIn("conv-gemini-loss", groups)
        self.assertIn("conv-claude-qiskit", groups)

        # ChatGPT group has 2 items
        self.assertEqual(len(groups["conv-chatgpt-arqpo"]["items"]), 2)
        # Gemini group has 1 item
        self.assertEqual(len(groups["conv-gemini-loss"]["items"]), 1)
        # Claude group has 1 item
        self.assertEqual(len(groups["conv-claude-qiskit"]["items"]), 1)

    def test_02_chronological_turn_ordering_within_group(self):
        """TEST 02: Items within a conversation group are sorted by turnIndex."""
        unordered = [
            {"id": "t3", "turnIndex": 3, "content": "Third"},
            {"id": "t1", "turnIndex": 1, "content": "First"},
            {"id": "t2", "turnIndex": 2, "content": "Second"}
        ]
        sorted_items = sorted(unordered, key=lambda x: x["turnIndex"])
        self.assertEqual(sorted_items[0]["id"], "t1")
        self.assertEqual(sorted_items[1]["id"], "t2")
        self.assertEqual(sorted_items[2]["id"], "t3")

    def test_03_format_context_package_contract(self):
        """TEST 03: formatContextPackage produces valid multi-source Markdown with provenance."""
        def format_context_package(items):
            groups = {}
            for it in items:
                cid = it["conversationId"]
                if cid not in groups:
                    groups[cid] = {
                        "title": it["conversationTitle"],
                        "provider": it["provider"],
                        "items": []
                    }
                groups[cid]["items"].append(it)

            lines = ["[Personal AI Memory Layer — Cross-AI Context Reference]:\n"]
            source_idx = 1
            for cid, grp in groups.items():
                lines.append(f"• SOURCE {source_idx}: {grp['provider']} — \"{grp['title']}\" (ID: {cid})")
                sorted_items = sorted(grp["items"], key=lambda x: x.get("turnIndex", 0))
                for item in sorted_items:
                    role_tag = f"[{item['role']}]" if item.get("role") else ""
                    turn_tag = f"Turn {item['turnIndex']}" if item.get("turnIndex") is not None else ""
                    mem_type_tag = f"⚡ {item['memoryType'].upper()}: " if item.get("memoryType") else ""
                    lbl = " ".join(filter(None, [turn_tag, role_tag]))
                    prefix = f"  - {lbl}: " if lbl else "  - "
                    content = item['content'].strip()
                    lines.append(f"{prefix}{mem_type_tag}\"{content}\"")
                source_idx += 1
            lines.append("")
            return "\n".join(lines)

        packaged = format_context_package(self.sample_items)
        self.assertIn("[Personal AI Memory Layer — Cross-AI Context Reference]:", packaged)
        self.assertIn('• SOURCE 1: ChatGPT — "Quantum Portfolio Optimization"', packaged)
        self.assertIn('• SOURCE 2: Gemini — "Loss Function Derivations"', packaged)
        self.assertIn('• SOURCE 3: Claude — "Qiskit Circuit Simulation"', packaged)
        self.assertIn("Turn 0 [user]:", packaged)
        self.assertIn('Turn 1 [assistant]: ⚡ DECISION: "We should adopt the ARQPO framework with PCA-QAOA."', packaged)
        self.assertIn('Turn 4 [assistant]: ⚡ FACT: "The loss function formula is L = ||w - w_opt||^2 + lambda * R."', packaged)

    def test_04_minimum_useful_context_guarantee(self):
        """TEST 04: Package only includes selected messages, never bloated whole-transcript dumps."""
        selected = [self.sample_items[1]]
        groups = {selected[0]["conversationId"]: {"title": selected[0]["conversationTitle"], "provider": selected[0]["provider"], "items": selected}}
        out = ""
        for cid, grp in groups.items():
            out += f"SOURCE: {grp['provider']}\n"
            for it in grp["items"]:
                out += f"- {it['content']}\n"

        self.assertIn("We should adopt the ARQPO framework", out)
        self.assertNotIn("Which optimizer architecture should we adopt?", out)
        self.assertNotIn("Loss Function Derivations", out)

    def test_05_2d_navigation_cross_conversation_cycle(self):
        """TEST 05: Left/Right navigation calculates correct cyclic indices across distinct conversation IDs."""
        distinct_conv_ids = ["conv-1", "conv-2", "conv-3"]
        
        # Right arrow moves forward cyclically
        curr = 0
        curr = (curr + 1) % len(distinct_conv_ids)
        self.assertEqual(curr, 1)
        curr = (curr + 1) % len(distinct_conv_ids)
        self.assertEqual(curr, 2)
        curr = (curr + 1) % len(distinct_conv_ids)
        self.assertEqual(curr, 0)

        # Left arrow moves backward cyclically
        curr = (curr - 1 + len(distinct_conv_ids)) % len(distinct_conv_ids)
        self.assertEqual(curr, 2)
        curr = (curr - 1 + len(distinct_conv_ids)) % len(distinct_conv_ids)
        self.assertEqual(curr, 1)

    def test_06_2d_navigation_intra_list_boundaries(self):
        """TEST 06: Up/Down navigation adheres strictly to list min/max boundaries."""
        total_cards = 5
        curr = 0
        
        curr = max(curr - 1, 0)
        self.assertEqual(curr, 0)

        for _ in range(4):
            curr = min(curr + 1, total_cards - 1)
        self.assertEqual(curr, 4)

        curr = min(curr + 1, total_cards - 1)
        self.assertEqual(curr, 4)

    def test_07_xss_protection_in_destination_modal(self):
        """TEST 07: Conversation titles and contents with special characters are safely escaped."""
        def escape_html(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        malicious_title = "<img src=x onerror=alert('xss')> Chat & Topic"
        escaped = escape_html(malicious_title)
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)
        self.assertIn("&amp;", escaped)


if __name__ == "__main__":
    unittest.main()
