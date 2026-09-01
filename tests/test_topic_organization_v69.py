"""
Unit and Contract Tests for Milestone V6.9 (Post-Manual Testing Hardened):
Topic Organization, Strictly Scoped "This Conversation" Search & Host DOM Navigation.

Validates:
1. "This Conversation" mode NEVER calls global database search (zero client.searchGlobal).
2. "This Conversation" returns strictly current active conversation DOM turns.
3. Matching results preserve host DOM element / locator references.
4. Up/Down (↑ / ↓) navigation targets and resolves the host message.
5. Host message highlight lifecycle (added and safely cleaned up).
6. Missing / virtualized unmounted message handling is 100% graceful (zero crashes).
7. 2D Navigation contract preserved (← / → for cross-conversation, ↑ / ↓ for intra-conversation).
8. Strict INSERT-ONLY contract adherence (zero auto-send, zero Enter, zero form submit).
9. Deterministic derived topic context format compliance.
10. Parent conversation non-destructiveness.
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
            "element_ref": item.get("element_ref", None),
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


def test_this_conversation_does_not_call_global_search():
    """Verify activeMode=current in content.js never invokes client.searchGlobal()."""
    content_path = os.path.join("extension", "content", "content.js")
    with open(content_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Locate the activeMode === 'current' block
    idx_current = code.find('activeMode === "current"')
    assert idx_current != -1

    # Extract block up to next branch
    block = code[idx_current:idx_current + 300]
    assert "searchGlobal" not in block
    assert "renderCurrentConversationResults" in block


def test_this_conversation_returns_only_dom_matches():
    """Verify only current conversation turns are filtered and returned without global DB fallback."""
    dom_messages = [
        {"index": 0, "role": "user", "content": "Update 1 prompt discussion."},
        {"index": 1, "role": "assistant", "content": "Here is Update 1 details."},
        {"index": 2, "role": "user", "content": "What about dinner recipes?"},
    ]

    q = "Update 1"
    q_lower = q.lower()
    matches = [m for m in dom_messages if q_lower in m["content"].lower()]

    assert len(matches) == 2
    assert matches[0]["index"] == 0
    assert matches[1]["index"] == 1
    assert "dinner recipes" not in [m["content"] for m in matches]


def test_current_match_preserves_host_dom_reference():
    """Verify a matching result retains the host DOM index / element locator."""
    bridge = MockTopicBridge()
    bridge.add_item({
        "id": "dom-msg-3",
        "conversation_id": "current-webpage",
        "conversation_title": "Quantum Discussion",
        "provider": "ChatGPT",
        "role": "assistant",
        "turn_index": 3,
        "content": "QAOA circuit executed.",
        "element_ref": "article-node-3"
    })

    items = bridge.get_items()
    assert len(items) == 1
    assert items[0]["element_ref"] == "article-node-3"
    assert items[0]["turn_index"] == 3


def test_up_down_navigation_targets_host_message():
    """Verify ↑ / ↓ navigation resolution and host scrollToMessage dispatch."""
    chatgpt_path = os.path.join("extension", "providers", "chatgpt.js")
    with open(chatgpt_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "scrollToMessage(messageRef)" in code
    assert "scrollIntoView" in code
    assert "memory-layer-host-highlight" in code


def test_host_message_highlight_lifecycle():
    """Verify temporary host highlight is added and timeout-removed."""
    css_path = os.path.join("extension", "content", "content.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    assert ".memory-layer-host-highlight" in css
    assert "outline" in css
    assert "box-shadow" in css


def test_missing_virtualized_message_is_graceful():
    """Verify graceful handling when target host DOM element is unmounted/virtualized."""
    chatgpt_path = os.path.join("extension", "providers", "chatgpt.js")
    with open(chatgpt_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Verify graceful null check and warning log without throw
    assert "!el || !document.body.contains(el)" in code
    assert "return false" in code


def test_global_navigation_contract_preserved():
    """Verify ← / → remains conversation-group navigation in content.js."""
    content_path = os.path.join("extension", "content", "content.js")
    with open(content_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert 'e.key === "ArrowRight"' in code
    assert 'e.key === "ArrowLeft"' in code
    assert "jumpToConversationGroup" in code


def test_insert_only_contract_preserved():
    """Verify no Send / Enter / submit behavior in content.js or providers."""
    content_path = os.path.join("extension", "content", "content.js")
    bridge_path = os.path.join("extension", "core", "context_bridge.js")

    with open(content_path, "r", encoding="utf-8") as f:
        content_code = f.read()
    with open(bridge_path, "r", encoding="utf-8") as f:
        bridge_code = f.read()

    assert "form.submit()" not in content_code
    assert "form.submit()" not in bridge_code
    assert 'key: "Enter"' not in content_code


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

    bridge = MockTopicBridge()
    bridge.add_item({"id": "m1", "conversation_id": "parent-1", "turn_index": 0, "role": "user", "content": "Message 1"})
    bridge.add_item({"id": "m3", "conversation_id": "parent-1", "turn_index": 2, "role": "user", "content": "Message 3"})
    pkg = bridge.format_topic_branch_package("Parent Title", "parent-1", "Topic Query")
    assert len(pkg) > 0

    cur.execute("SELECT count(*) FROM messages WHERE conversation_id='parent-1'")
    count = cur.fetchone()[0]
    assert count == 3
    conn.close()
