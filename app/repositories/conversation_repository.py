"""
Repository layer for Conversations and Messages data access.
Abstracts all SQL queries and database operations behind clean Python methods.
Auto-indexes embeddings for semantic search upon save with explicit error logging.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from app.models.schemas import Conversation, Message
from app.repositories.database import Database

logger = logging.getLogger(__name__)


class ConversationRepository:
    """
    Handles persistence, retrieval, updating, and deletion of Conversations and Messages.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def find_duplicate_id(self, conversation: Conversation) -> Optional[str]:
        """
        Checks if an identical conversation already exists in the database.
        Matches by exact ID OR by (title, source, message_count, and first message snippet).
        Returns the existing conversation ID if found, otherwise None.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Exact ID check
            cursor.execute("SELECT id FROM conversations WHERE id = ?", (conversation.id,))
            row = cursor.fetchone()
            if row:
                return row["id"]

            # 2. Title + Source match check
            cursor.execute(
                "SELECT id FROM conversations WHERE title = ? AND source = ?",
                (conversation.title, conversation.source),
            )
            candidate_rows = cursor.fetchall()
            if not candidate_rows:
                return None

            first_snippet = conversation.messages[0].content[:100] if conversation.messages else ""

            for c_row in candidate_rows:
                c_id = c_row["id"]
                cursor.execute("SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?", (c_id,))
                cnt = cursor.fetchone()["cnt"]

                if cnt == conversation.message_count:
                    # Compare first message snippet
                    cursor.execute(
                        "SELECT content FROM messages WHERE conversation_id = ? AND msg_index = 0",
                        (c_id,),
                    )
                    first_msg_row = cursor.fetchone()
                    if first_msg_row:
                        existing_snippet = first_msg_row["content"][:100]
                        if existing_snippet == first_snippet:
                            return c_id

            return None

    def is_duplicate(self, conversation: Conversation) -> bool:
        """Returns True if the conversation is a duplicate of an existing record."""
        return self.find_duplicate_id(conversation) is not None

    def save_conversation(self, conversation: Conversation) -> str:
        """
        Saves a conversation and all its messages into the database in a single atomic transaction.
        Also triggers embedding generation for semantic search with explicit error reporting.
        Returns the conversation ID.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            tags_str = ",".join(conversation.tags) if conversation.tags else ""

            cursor.execute(
                """
                INSERT OR REPLACE INTO conversations 
                (id, title, source, imported_at, original_date, category, tags, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.id,
                    conversation.title,
                    conversation.source,
                    conversation.imported_at,
                    conversation.original_date,
                    conversation.category,
                    tags_str,
                    conversation.description,
                ),
            )

            # Insert messages with optional provenance references
            for msg in conversation.messages:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO messages
                    (id, conversation_id, role, content, msg_index, timestamp, source_conversation_id, source_message_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        conversation.id,
                        msg.role,
                        msg.content,
                        msg.index,
                        msg.timestamp,
                        msg.source_conversation_id,
                        msg.source_message_id,
                    ),
                )

            conn.commit()

        # Generate semantic embeddings for saved conversation
        self._index_embeddings(conversation)
        return conversation.id

    def _index_embeddings(self, conversation: Conversation):
        """Helper to generate and persist message embeddings with explicit error reporting."""
        try:
            from app.search.semantic_search import SemanticSearchEngine
            semantic_engine = SemanticSearchEngine(self)
            indexed_count = semantic_engine.index_conversation_messages(conversation.id)
            logger.info(f"Successfully generated embeddings for {indexed_count} message(s) in '{conversation.title}'")
        except Exception as e:
            logger.error(f"Failed to generate vector embeddings for conversation '{conversation.title}': {e}")
            # Re-raise so caller/UI does not claim false success if indexing failed
            raise RuntimeError(f"Embedding generation failed: {e}")

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Retrieves a conversation by ID, along with all of its ordered messages.
        Returns None if not found.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                """
                SELECT * FROM messages 
                WHERE conversation_id = ? 
                ORDER BY msg_index ASC
                """,
                (conversation_id,),
            )
            msg_rows = cursor.fetchall()

            messages = [
                Message(
                    id=m["id"],
                    conversation_id=m["conversation_id"],
                    role=m["role"],
                    content=m["content"],
                    index=m["msg_index"],
                    timestamp=m["timestamp"],
                    source_conversation_id=m["source_conversation_id"] if "source_conversation_id" in m.keys() else None,
                    source_message_id=m["source_message_id"] if "source_message_id" in m.keys() else None,
                )
                for m in msg_rows
            ]

            tags_list = [t.strip() for t in row["tags"].split(",") if t.strip()] if row["tags"] else []

            return Conversation(
                id=row["id"],
                title=row["title"],
                source=row["source"],
                imported_at=row["imported_at"],
                original_date=row["original_date"],
                category=row["category"],
                tags=tags_list,
                description=row["description"],
                messages=messages,
            )

    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        """
        Lists all stored conversations sorted by imported_at DESC (most recent first).
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id FROM conversations 
                ORDER BY imported_at DESC 
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()

            conversations = []
            for row in rows:
                conv = self.get_conversation(row["id"])
                if conv:
                    conversations.append(conv)
            return conversations

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Deletes a conversation and its messages/embeddings (via ON DELETE CASCADE).
        Returns True if deleted, False if conversation did not exist.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    def update_metadata(
        self,
        conversation_id: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Updates metadata for an existing conversation and re-indexes embeddings.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if category is not None:
                updates.append("category = ?")
                params.append(category)
            if tags is not None:
                updates.append("tags = ?")
                params.append(",".join(tags))
            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if not updates:
                return False

            params.append(conversation_id)
            sql = f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(sql, tuple(params))
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            conv = self.get_conversation(conversation_id)
            if conv:
                self._index_embeddings(conv)

        return updated

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns high-level statistics about stored conversations and messages.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as total FROM conversations")
            total_conversations = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as total FROM messages")
            total_messages = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT source, COUNT(*) as count 
                FROM conversations 
                GROUP BY source
            """)
            source_rows = cursor.fetchall()
            sources = {r["source"]: r["count"] for r in source_rows}

            return {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "sources": sources,
            }

    def add_relationship(
        self,
        parent_id: str,
        child_id: str,
        topic: str,
        rel_type: str = "topic_continuation",
    ) -> str:
        """
        Stores a parent-child conversation relationship (Version 3 Feature 2: Continue Topic).
        Returns the created relationship ID.
        """
        import uuid
        from datetime import datetime, timezone

        rel_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_relationships
                (id, parent_conversation_id, child_conversation_id, relationship_type, topic, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rel_id, parent_id, child_id, rel_type, topic, created_at),
            )
            conn.commit()
        return rel_id

    def get_relationships(self, conversation_id: str) -> Dict[str, Any]:
        """
        Returns relationship metadata for a conversation.
        Includes parent conversation info (if this is a child continuation)
        and children conversations info (if topics were extracted from this conversation).
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Find parent (if child)
            cursor.execute(
                """
                SELECT r.*, c.title as parent_title 
                FROM conversation_relationships r
                JOIN conversations c ON r.parent_conversation_id = c.id
                WHERE r.child_conversation_id = ?
                """,
                (conversation_id,),
            )
            parent_row = cursor.fetchone()

            # Find children (if parent)
            cursor.execute(
                """
                SELECT r.*, c.title as child_title 
                FROM conversation_relationships r
                JOIN conversations c ON r.child_conversation_id = c.id
                WHERE r.parent_conversation_id = ?
                """,
                (conversation_id,),
            )
            children_rows = cursor.fetchall()

            parent_info = (
                {
                    "relationship_id": parent_row["id"],
                    "parent_id": parent_row["parent_conversation_id"],
                    "parent_title": parent_row["parent_title"],
                    "topic": parent_row["topic"],
                    "created_at": parent_row["created_at"],
                }
                if parent_row
                else None
            )

            children_info = [
                {
                    "relationship_id": r["id"],
                    "child_id": r["child_conversation_id"],
                    "child_title": r["child_title"],
                    "topic": r["topic"],
                    "created_at": r["created_at"],
                }
                for r in children_rows
            ]

            return {
                "parent": parent_info,
                "children": children_info,
            }
