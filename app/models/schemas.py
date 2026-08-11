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
