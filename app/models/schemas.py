"""
Provider-independent data schemas for Conversations and Messages.

Why this exists:
Different AI providers (ChatGPT, Gemini, Claude, Perplexity) export conversation data
in different JSON/text formats. Standardizing into a unified schema decoupling the 
storage, search, and UI components from vendor-specific details.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid


@dataclass
class Message:
    """
    Represents an individual message within a conversation.
    """
    role: str  # 'user', 'assistant', 'system'
    content: str
    index: int  # 0-indexed position within conversation
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: Optional[str] = None
    timestamp: Optional[str] = None
    source_conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "index": self.index,
            "timestamp": self.timestamp,
            "source_conversation_id": self.source_conversation_id,
            "source_message_id": self.source_message_id,
        }


@dataclass
class Conversation:
    """
    Represents an imported conversation containing zero or more Messages.
    """
    title: str
    messages: List[Message] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "Unknown"  # e.g., 'ChatGPT', 'Gemini', 'Claude', 'TXT', 'JSON'
    imported_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    original_date: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None

    def __post_init__(self):
        # Assign conversation_id to all child messages if missing
        for idx, msg in enumerate(self.messages):
            msg.conversation_id = self.id
            if msg.index is None:
                msg.index = idx

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "imported_at": self.imported_at,
            "original_date": self.original_date,
            "message_count": self.message_count,
            "category": self.category,
            "tags": self.tags,
            "description": self.description,
            "messages": [m.to_dict() for m in self.messages],
        }


@dataclass
class ContextCandidate:
    """
    Represents a candidate message retrieved during multi-topic context search.
    """
    message_id: str
    conversation_id: str
    conversation_title: str
    source: str
    role: str
    content: str
    message_index: int
    relevance_score: int
    timestamp: Optional[str] = None
    topic_association: Optional[str] = None
    raw_semantic_score: float = 0.0
    keyword_score: int = 0
    is_derived: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "conversation_title": self.conversation_title,
            "source": self.source,
            "role": self.role,
            "content": self.content,
            "message_index": self.message_index,
            "relevance_score": self.relevance_score,
            "timestamp": self.timestamp,
            "topic_association": self.topic_association,
            "raw_semantic_score": self.raw_semantic_score,
            "keyword_score": self.keyword_score,
            "is_derived": self.is_derived,
        }


@dataclass
class ComposedContext:
    """
    Represents a package of selected, ordered context blocks derived from multiple source conversations.
    """
    composition_id: str
    title: str
    query: str
    selected_candidates: List[ContextCandidate] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def source_conversations(self) -> List[Dict[str, str]]:
        unique = {}
        for c in self.selected_candidates:
            if c.conversation_id not in unique:
                unique[c.conversation_id] = {
                    "id": c.conversation_id,
                    "title": c.conversation_title,
                    "source": c.source,
                }
        return list(unique.values())

    @property
    def source_providers(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for c in self.selected_candidates:
            counts[c.source] = counts.get(c.source, 0) + 1
        return counts

    def export(self) -> Dict[str, Any]:
        """
        Export provider-independent context payload structure for future AI provider destinations (Version 5).
        """
        return {
            "composition_id": self.composition_id,
            "title": self.title,
            "composition_query": self.query,
            "created_at": self.created_at,
            "total_messages": len(self.selected_candidates),
            "source_conversations": self.source_conversations,
            "source_providers": self.source_providers,
            "messages": [c.to_dict() for c in self.selected_candidates],
        }


@dataclass
class PortableContextPackage:
    """
    V5A — Provider-Independent Versioned Portable Context Package.
    Establishes the clean contract between V4 Context Composition and V5 AI Destinations.
    """
    package_id: str
    title: str
    topic: str
    context_text: str
    source_conversations: List[Dict[str, str]] = field(default_factory=list)
    source_providers: Dict[str, int] = field(default_factory=dict)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "title": self.title,
            "topic": self.topic,
            "created_at": self.created_at,
            "total_messages": len(self.messages),
            "source_conversations": self.source_conversations,
            "source_providers": self.source_providers,
            "context_text": self.context_text,
            "messages": self.messages,
            "provenance": self.provenance,
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)
