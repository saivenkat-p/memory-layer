"""
Topic Extraction and Continuation Engine Service (Version 3 Feature 2: Continue Topic).

Handles:
1. Topic Context Extraction: Embeds topic description, scores messages in target conversation,
   preserves user/assistant response pairs, and orders chronologically (80 -> 84 -> 91).
2. Focused Conversation Creation: Instantiates derived conversation titled 'Continued: <Topic>',
   links source_conversation_id and source_message_id provenance references, and records
   parent-child relationships in SQLite.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from app.models.schemas import Conversation, Message
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine

logger = logging.getLogger(__name__)


@dataclass
class TopicMessageSelection:
    """Represents an individual message selected during topic context extraction."""
    message_id: str
    original_index: int
    role: str
    content: str
    similarity_score: float
    is_direct_match: bool  # True if scored above threshold, False if added for context continuity


@dataclass
class TopicContextPreview:
    """Container holding extracted topic context preview for user inspection."""
    parent_conversation_id: str
    parent_title: str
    topic: str
    selected_messages: List[TopicMessageSelection] = field(default_factory=list)
    direct_match_count: int = 0
    total_context_messages: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_conversation_id": self.parent_conversation_id,
            "parent_title": self.parent_title,
            "topic": self.topic,
            "direct_match_count": self.direct_match_count,
            "total_context_messages": self.total_context_messages,
            "selected_messages": [
                {
                    "message_id": m.message_id,
                    "original_index": m.original_index,
                    "role": m.role,
                    "content": m.content,
                    "similarity_score": m.similarity_score,
                    "is_direct_match": m.is_direct_match,
                }
                for m in self.selected_messages
            ],
        }


class TopicExtractionEngine:
    """
    Service that extracts focused topic contexts from long multi-topic conversations
    and instantiates derived continuation conversations.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        min_similarity_threshold: float = 0.28,
    ):
        self.repo = repo or ConversationRepository()
        self.semantic_engine = SemanticSearchEngine(self.repo)
        self.min_similarity_threshold = min_similarity_threshold

    def extract_topic_context(
        self,
        conversation_id: str,
        topic_query: str,
        min_similarity: Optional[float] = None,
    ) -> TopicContextPreview:
        """
        Extracts messages relevant to topic_query from target conversation.

        Args:
            conversation_id: ID of the parent conversation.
            topic_query: User's topic description (e.g. 'Personal AI Memory Layer').
            min_similarity: Optional custom similarity threshold (defaults to 0.28).

        Returns:
            TopicContextPreview container.
        """
        threshold = min_similarity if min_similarity is not None else self.min_similarity_threshold

        conv = self.repo.get_conversation(conversation_id)
        if not conv or not conv.messages or not topic_query or not topic_query.strip():
            return TopicContextPreview(
                parent_conversation_id=conversation_id,
                parent_title=conv.title if conv else "Unknown",
                topic=topic_query,
            )

        clean_topic = topic_query.strip()
        topic_vec = self.semantic_engine.generate_embedding(clean_topic)

        import numpy as np

        # 1. Score all messages in conversation
        message_scores: Dict[int, float] = {}
        topic_np = np.asarray(topic_vec, dtype=np.float32)

        for msg in conv.messages:
            msg_text = f"{msg.role}: {msg.content}"
            msg_vec = self.semantic_engine.generate_embedding(msg_text)
            msg_np = np.asarray(msg_vec, dtype=np.float32)

            if len(topic_np) == len(msg_np) and len(topic_np) > 0:
                sim = float(np.dot(topic_np, msg_np))
                sim = max(-1.0, min(1.0, sim))
            else:
                sim = 0.0

            # Also boost if topic keywords literally appear in message content
            if any(term in msg.content.lower() for term in clean_topic.lower().split() if len(term) > 3):
                sim = max(sim, 0.45)
            message_scores[msg.index] = sim

        # 2. Identify direct matches above threshold
        direct_match_indices = {
            idx for idx, score in message_scores.items() if score >= threshold
        }

        # If no messages pass threshold, take top 2 highest scoring messages
        if not direct_match_indices and message_scores:
            sorted_indices = sorted(message_scores.keys(), key=lambda i: message_scores[i], reverse=True)
            direct_match_indices = set(sorted_indices[:2])

        # 3. Context Window Expansion: Add adjacent assistant/user pairs for coherence
        selected_indices = set()
        for idx in direct_match_indices:
            selected_indices.add(idx)
            # If user message matched, include immediate assistant response if available
            if idx + 1 in message_scores and conv.messages[idx].role == "user":
                selected_indices.add(idx + 1)
            # If assistant message matched, include immediate user question if available
            if idx - 1 in message_scores and conv.messages[idx].role == "assistant":
                selected_indices.add(idx - 1)

        # 4. Sort indices to enforce strict chronological order (e.g. 80 -> 84 -> 91)
        ordered_indices = sorted(list(selected_indices))

        selected_items: List[TopicMessageSelection] = []
        for idx in ordered_indices:
            msg = conv.messages[idx]
            is_direct = idx in direct_match_indices
            sim = message_scores.get(idx, 0.0)
            selected_items.append(
                TopicMessageSelection(
                    message_id=msg.id,
                    original_index=msg.index,
                    role=msg.role,
                    content=msg.content,
                    similarity_score=round(sim, 4),
                    is_direct_match=is_direct,
                )
            )

        return TopicContextPreview(
            parent_conversation_id=conv.id,
            parent_title=conv.title,
            topic=clean_topic,
            selected_messages=selected_items,
            direct_match_count=len(direct_match_indices),
            total_context_messages=len(selected_items),
        )

    def create_continued_conversation(
        self,
        parent_conversation_id: str,
        topic: str,
        selected_message_ids: List[str],
    ) -> Conversation:
        """
        Creates and stores a derived focused conversation containing ONLY the extracted topic context.

        Args:
            parent_conversation_id: Parent conversation ID.
            topic: Topic description string.
            selected_message_ids: List of message IDs selected for inclusion.

        Returns:
            Newly created child Conversation instance.
        """
        parent_conv = self.repo.get_conversation(parent_conversation_id)
        if not parent_conv:
            raise ValueError(f"Parent conversation '{parent_conversation_id}' not found.")

        # Filter and maintain parent chronological order
        selected_set = set(selected_message_ids)
        extracted_msgs: List[Message] = []

        for orig_msg in parent_conv.messages:
            if orig_msg.id in selected_set:
                extracted_msgs.append(
                    Message(
                        role=orig_msg.role,
                        content=orig_msg.content,
                        index=len(extracted_msgs),
                        timestamp=orig_msg.timestamp,
                        source_conversation_id=parent_conv.id,
                        source_message_id=orig_msg.id,
                    )
                )

        child_title = f"Continued: {topic.strip().title()}"
        child_conv = Conversation(
            title=child_title,
            messages=extracted_msgs,
            source=parent_conv.source,
            category=parent_conv.category or "Topic Continuation",
            tags=list(set(parent_conv.tags + ["Continuation", topic.strip()])),
            description=f"Focused topic continuation extracted from '{parent_conv.title}' on topic '{topic}'.",
        )

        # Save child conversation to SQLite repository
        self.repo.save_conversation(child_conv)

        # Record parent-child relationship in conversation_relationships
        self.repo.add_relationship(
            parent_id=parent_conv.id,
            child_id=child_conv.id,
            topic=topic.strip(),
            rel_type="topic_continuation",
        )

        return child_conv
