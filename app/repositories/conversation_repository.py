"""
Repository layer for Conversations and Messages data access.
Abstracts all SQL queries and database operations behind clean Python methods.
Auto-indexes embeddings for semantic search upon save.
"""

import json
from typing import List, Optional, Dict, Any
from app.models.schemas import Conversation, Message
from app.repositories.database import Database


class ConversationRepository:
    """
    Handles persistence, retrieval, updating, and deletion of Conversations and Messages.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def save_conversation(self, conversation: Conversation) -> str:
        """
        Saves a conversation and all its messages into the database in a single atomic transaction.
        Also triggers embedding generation for semantic search.
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

            # Insert messages
            for msg in conversation.messages:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO messages
                    (id, conversation_id, role, content, msg_index, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.id,
                        conversation.id,
                        msg.role,
                        msg.content,
                        msg.index,
                        msg.timestamp,
                    ),
                )

            conn.commit()

        # Generate semantic embeddings for saved conversation
        self._index_embeddings(conversation)
        return conversation.id

    def _index_embeddings(self, conversation: Conversation):
        """Helper to generate and persist message embeddings."""
        try:
            from app.search.semantic_search import SemanticSearchEngine
            semantic_engine = SemanticSearchEngine(self)
            semantic_engine.index_conversation_messages(conversation.id)
        except Exception:
            pass

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

            # Retrieve associated messages sorted by msg_index
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
