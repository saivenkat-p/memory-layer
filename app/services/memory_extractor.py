"""
Memory Extractor Service Layer (Milestone V6.5-E1).

Provides an abstract interface and a deterministic/offline rule-based implementation
for extracting candidate StructuredMemory objects from raw conversations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re
from app.models.schemas import Conversation, Message, StructuredMemory


class BaseMemoryExtractor(ABC):
    """
    Abstract base class defining the provider-independent memory extraction interface.
    """

    @abstractmethod
    def extract_memories(self, conversation: Conversation) -> List[StructuredMemory]:
        """
        Extracts candidate structured memories from a conversation.
        """
        pass


class DeterministicMemoryExtractor(BaseMemoryExtractor):
    """
    Offline, deterministic rule-based memory extractor for Milestone V6.5-E1.

    Guarantees reproducible extraction of structured memories (decisions, preferences,
    facts, project goals) without external LLM calls or network latency.
    """

    DECISION_PATTERNS = [
        r"(?:decided to|let's use|we will use|we chose|decision:)\s+([^.\
]+)",
        r"(?:approved|selected)\s+([^.\
]+)",
    ]

    PREFERENCE_PATTERNS = [
        r"(?:i prefer|my preference is|i always use|i like)\s+([^.\
]+)",
    ]

    GOAL_PATTERNS = [
        r"(?:goal is|project goal:|target is|objective:)\s+([^.\
]+)",
    ]

    FACT_PATTERNS = [
        r"(?:note that|remember that|the fact is)\s+([^.\
]+)",
    ]

    def extract_memories(self, conversation: Conversation) -> List[StructuredMemory]:
        """
        Scans conversation messages and extracts candidate memories using deterministic pattern matching.
        Also detects multi-turn dialogue patterns where a user proposes and assistant/user confirms.
        """
        memories: List[StructuredMemory] = []
        messages = conversation.messages

        if not messages:
            return memories

        # 1. Single-turn pattern extraction
        for idx, msg in enumerate(messages):
            text = msg.content

            # Decisions
            for pat in self.DECISION_PATTERNS:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    content = match.group(0).strip()
                    memories.append(
                        StructuredMemory(
                            conversation_id=conversation.id,
                            memory_type="decision",
                            content=content,
                            start_msg_index=idx,
                            end_msg_index=idx,
                            source_message_ids=[msg.id],
                            provider=conversation.source,
                            confidence=1.0,
                            status="active",
                        )
                    )
                    break

            # Preferences
            for pat in self.PREFERENCE_PATTERNS:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    content = match.group(0).strip()
                    memories.append(
                        StructuredMemory(
                            conversation_id=conversation.id,
                            memory_type="preference",
                            content=content,
                            start_msg_index=idx,
                            end_msg_index=idx,
                            source_message_ids=[msg.id],
                            provider=conversation.source,
                            confidence=1.0,
                            status="active",
                        )
                    )
                    break

            # Project Goals
            for pat in self.GOAL_PATTERNS:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    content = match.group(0).strip()
                    memories.append(
                        StructuredMemory(
                            conversation_id=conversation.id,
                            memory_type="project_goal",
                            content=content,
                            start_msg_index=idx,
                            end_msg_index=idx,
                            source_message_ids=[msg.id],
                            provider=conversation.source,
                            confidence=1.0,
                            status="active",
                        )
                    )
                    break

            # Facts
            for pat in self.FACT_PATTERNS:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    content = match.group(0).strip()
                    memories.append(
                        StructuredMemory(
                            conversation_id=conversation.id,
                            memory_type="fact",
                            content=content,
                            start_msg_index=idx,
                            end_msg_index=idx,
                            source_message_ids=[msg.id],
                            provider=conversation.source,
                            confidence=1.0,
                            status="active",
                        )
                    )
                    break

        # 2. Multi-turn decision extraction (Proposal in turn i -> Agreement/Confirmation in turn i+1 or i+2)
        for i in range(len(messages) - 1):
            msg_u = messages[i]
            msg_next = messages[i + 1]

            # Check for user proposal and assistant confirmation
            if msg_u.role == "user" and msg_next.role == "assistant":
                if ("how should we" in msg_u.content.lower() or "should we use" in msg_u.content.lower()) and (
                    "recommend" in msg_next.content.lower() or "suggest" in msg_next.content.lower()
                ):
                    # Multi-turn span across i and i+1
                    # If there's a following user agreement at i+2, include it
                    end_idx = i + 1
                    source_ids = [msg_u.id, msg_next.id]
                    if i + 2 < len(messages) and any(
                        w in messages[i + 2].content.lower() for w in ["yes", "approved", "let's do it", "sounds good"]
                    ):
                        end_idx = i + 2
                        source_ids.append(messages[i + 2].id)

                    memories.append(
                        StructuredMemory(
                            conversation_id=conversation.id,
                            memory_type="decision",
                            content=f"Agreed architecture decision from multi-turn discussion (turns {i}-{end_idx})",
                            start_msg_index=i,
                            end_msg_index=end_idx,
                            source_message_ids=source_ids,
                            provider=conversation.source,
                            confidence=1.0,
                            status="active",
                        )
                    )

        return memories
