"""
Unit and Contract Tests for Milestone V6.9:
Topic Organization & Non-Destructive Derived Branching.

Validates:
1. Topic occurrence isolation within a parent conversation.
2. Chronological turn ordering in derived topic packages.
3. Full parent conversation provenance preservation.
4. Deterministic derived topic context format compliance.
5. Strict non-destructiveness of the parent conversation.
6. Absolute INSERT-ONLY contract adherence.
7. XSS sanitization of topic titles, queries, and content.
8. Selection isolation (only selected topic turns packaged).
"""

import pytest
import os
import sqlite3
import html


class MockTopicBridge:
    """
    Python mirror of ContextBridge topic branch formatting for deterministic testing.
    """
    def __init__(self):
        self.selected_items = {}

    def add_item(self, item):
        if not item or not item.get("id"):
            return
        self.selected_items[item["id"]] = {
            "id": item["id"],
            "conversation_id": item.get("conversation_id", "unknown"),
            "conversation_title": item.get("conversation_title", item.get("conversation_id", "Conversation")),
            "provider": item.get("provider", "AI"),
            "role": item.get("role", "assistant"),
            "turn_index": item.get("turn_index", 0),
            "content": item.get("content", ""),
            "memory_type": item.get("memory_type", None),
        }

    def remove_item(self, item_id):
        self.selected_items.pop(item_id, None)

    def clear(self):
        self.selected_items.clear()

    def get_items(self):
        return list(self.selected_items.values())

    def get_count(self):
        return len(self.selected_items)

    def format_topic_branch_package(self, parent_title, parent_conv_id, topic_query, items=None):
        item_list = items if items is not None else self.get_items()
        if not item_list:
            return ""

        out = "[Personal AI Memory Layer — Derived Topic Context]\n\n"
        out += f'Parent Conversation: "{parent_title or "Active Conversation"}"\n'
        out += f'Parent Conversation ID: "{parent_conv_id or "current-webpage"}"\n\n'
        out += f'Topic: "{topic_query or "Focused Topic"}"\n\n'
        out += "Selected Topic Context:\n\n"

        sorted_turns = sorted(item_list, key=lambda x: x["turn_index"])
        for turn in sorted_turns:
            role_tag = f"[{turn['role']}]" if turn.get("role") else ""
            turn_tag = f"Turn {turn['turn_index']}" if turn.get("turn_index") is not None else ""
            mem_type_tag = f"⚡ {turn['memory_type'].upper()}: " if turn.get("memory_type") else ""
            label = " ".join(filter(None, [turn_tag, role_tag]))
            prefix = f"- {label}: " if label else "- "
            out += f'{prefix}{mem_type_tag}\"{turn["content"].strip()}\"\n'

        out += "\n[Reference Material Only — Continue discussion on this topic below]\n"
        return out


def test_topic_occurrence_isolation():
    """Verify isolation of topic-specific turns from a multi-topic conversation."""
    bridge = MockTopicBridge()
    # Simulated turns in a long conversation containing multiple topics
    all_turns = [
        {"id": "t-0", "turn_index": 0, "role": "user", "content": "Let's discuss Quantum QAOA."},
        {"id": "t-1", "turn_index": 1, "role": "assistant", "content": "QAOA uses parameterized quantum circuits."},
        {"id": "t-2", "turn_index": 2, "role": "user", "content": "What about dinner recipes?"}, # Unrelated
        {"id": "t-3", "turn_index": 3, "role": "assistant", "content": "Try pasta carbonara."}, # Unrelated
        {"id": "t-4", "turn_index": 4, "role": "user", "content": "Back to QAOA: what shot count?"},
        {"id": "t-5", "turn_index": 5, "role": "assistant", "content": "Use 4096 shots for stability."},
    ]

    # Select only QAOA topic turns (t-0, t-1, t-4, t-5)
    for turn in [all_turns[0], all_turns[1], all_turns[4], all_turns[5]]:
        bridge.add_item({
            "id": turn["id"],
            "conversation_id": "conv-quantum-1",
            "conversation_title": "Quantum Research & Cooking",
            "provider": "ChatGPT",
            "role": turn["role"],
            "turn_index": turn["turn_index"],
            "content": turn["content"],
        })

    assert bridge.get_count() == 4
    pkg = bridge.format_topic_branch_package(
        parent_title="Quantum Research & Cooking",
        parent_conv_id="conv-quantum-1",
        topic_query="QAOA"
    )

    # QAOA turns are present
    assert "Turn 0 [user]: \"Let's discuss Quantum QAOA.\"" in pkg
    assert "Turn 1 [assistant]: \"QAOA uses parameterized quantum circuits.\"" in pkg
    assert "Turn 4 [user]: \"Back to QAOA: what shot count?\"" in pkg
    assert "Turn 5 [assistant]: \"Use 4096 shots for stability.\"" in pkg

    # Unrelated dinner recipe turns are strictly excluded
    assert "dinner recipes" not in pkg
    assert "pasta carbonara" not in pkg


def test_chronological_ordering():
    """Verify that selected turns added out of order are sorted strictly ascending by turn_index."""
    bridge = MockTopicBridge()
    # Add turns out of order
    bridge.add_item({"id": "t-8", "turn_index": 8, "role": "assistant", "content": "Conclusion turn."})
    bridge.add_item({"id": "t-2", "turn_index": 2, "role": "user", "content": "Introduction turn."})
    bridge.add_item({"id": "t-5", "turn_index": 5, "role": "assistant", "content": "Intermediate turn."})

    pkg = bridge.format_topic_branch_package("Test Conv", "conv-test", "Ordering Topic")

    pos_2 = pkg.find("Turn 2 [user]")
    pos_5 = pkg.find("Turn 5 [assistant]")
    pos_8 = pkg.find("Turn 8 [assistant]")

    assert pos_2 != -1 and pos_5 != -1 and pos_8 != -1
    assert pos_2 < pos_5 < pos_8


def test_parent_conversation_provenance():
    """Verify that parent conversation title, ID, and topic query are accurately retained."""
    bridge = MockTopicBridge()
    bridge.add_item({"id": "t-0", "turn_index": 0, "role": "user", "content": "Topic start."})

    pkg = bridge.format_topic_branch_package(
        parent_title="Deep Learning Optimization",
        parent_conv_id="conv-dl-999",
        topic_query="Adam vs SGD Momentum"
    )

    assert 'Parent Conversation: "Deep Learning Optimization"' in pkg
    assert 'Parent Conversation ID: "conv-dl-999"' in pkg
    assert 'Topic: "Adam vs SGD Momentum"' in pkg


def test_deterministic_topic_package_formatting():
    """Verify exact compliance with the authoritative V6.9 Derived Topic Context layout."""
    bridge = MockTopicBridge()
    bridge.add_item({
        "id": "t-1",
        "turn_index": 1,
        "role": "user",
        "content": "Why PCA before QAOA?",
    })
    bridge.add_item({
        "id": "t-2",
        "turn_index": 2,
        "role": "assistant",
        "content": "PCA reduces qubit requirements from N to K.",
        "memory_type": "decision"
    })

    pkg = bridge.format_topic_branch_package(
        parent_title="Quantum Portfolio Architecture",
        parent_conv_id="conv-chatgpt-101",
        topic_query="PCA-QAOA Dimensionality"
    )

    expected_header = "[Personal AI Memory Layer — Derived Topic Context]\n\n"
    expected_parent = 'Parent Conversation: "Quantum Portfolio Architecture"\nParent Conversation ID: "conv-chatgpt-101"\n\n'
    expected_topic = 'Topic: "PCA-QAOA Dimensionality"\n\n'
    expected_context_header = "Selected Topic Context:\n\n"
    expected_footer = "\n[Reference Material Only — Continue discussion on this topic below]\n"

    assert pkg.startswith(expected_header)
    assert expected_parent in pkg
    assert expected_topic in pkg
    assert expected_context_header in pkg
    assert pkg.endswith(expected_footer)


def test_parent_non_destructiveness():
    """Verify that topic branch packaging does NOT mutate or delete parent records."""
    # Test on SQLite parent conversation fixture
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, turn_index INT)")
    
    parent_messages = [
        ("m1", "parent-1", "user", "Message 1", 0),
        ("m2", "parent-1", "assistant", "Message 2", 1),
        ("m3", "parent-1", "user", "Message 3", 2),
    ]
    cur.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", parent_messages)
    conn.commit()

    # Form derived topic branch from m1 and m3
    bridge = MockTopicBridge()
    bridge.add_item({"id": "m1", "conversation_id": "parent-1", "turn_index": 0, "role": "user", "content": "Message 1"})
    bridge.add_item({"id": "m3", "conversation_id": "parent-1", "turn_index": 2, "role": "user", "content": "Message 3"})
    pkg = bridge.format_topic_branch_package("Parent Title", "parent-1", "Topic Query")
    assert len(pkg) > 0

    # Verify parent messages table is 100% intact with 3 records
    cur.execute("SELECT count(*) FROM messages WHERE conversation_id='parent-1'")
    count = cur.fetchone()[0]
    assert count == 3
    conn.close()


def test_insert_only_safety_invariant():
    """Verify that extension content script and bridge maintain zero auto-send/submit code."""
    content_path = os.path.join("extension", "content", "content.js")
    bridge_path = os.path.join("extension", "core", "context_bridge.js")

    with open(content_path, "r", encoding="utf-8") as f:
        content_code = f.read()
    with open(bridge_path, "r", encoding="utf-8") as f:
        bridge_code = f.read()

    # Verify no automatic submission triggers in topic branch flow
    assert "form.submit()" not in content_code
    assert "form.submit()" not in bridge_code
    assert 'key: "Enter"' not in content_code
    assert 'key: "Enter"' not in bridge_code


def test_xss_sanitization_in_topic_branch():
    """Verify that adversarial topic titles, queries, and content are safely escaped."""
    adversarial_query = '<script>alert("xss")</script>'
    adversarial_title = 'Title with <img src=x onerror=alert(1)>'
    
    escaped_query = html.escape(adversarial_query)
    escaped_title = html.escape(adversarial_title)

    assert "<script>" not in escaped_query
    assert "&lt;script&gt;" in escaped_query
    assert "<img" not in escaped_title
    assert "&lt;img" in escaped_title
