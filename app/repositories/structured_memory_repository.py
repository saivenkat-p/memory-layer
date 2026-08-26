"""
Repository layer for Structured Memory data access (Milestone V6.5-E1).

Provides persistence, retrieval, provenance validation, and resolution
for StructuredMemory objects backed by SQLite.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from app.models.schemas import StructuredMemory, Message
from app.repositories.database import Database

logger = logging.getLogger(__name__)


class ProvenanceValidationError(ValueError):
    """Raised when a StructuredMemory fails atomic provenance validation."""
    pass


class StructuredMemoryRepository:
    """
    Manages persistence and retrieval of structured memories with strict provenance verification.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def validate_provenance(self, memory: StructuredMemory) -> bool:
        """
        Strictly validates that a StructuredMemory is backed by genuine messages
        belonging to the specified conversation within the declared turn index range.

        Validation Invariants:
        1. Conversation exists in the database.
        2. start_msg_index <= end_msg_index.
        3. source_message_ids is non-empty.
        4. All message IDs exist in messages table and belong to memory.conversation_id.
        5. The messages match the declared [start_msg_index, end_msg_index] range.
        6. The number of verified messages matches len(source_message_ids).

        Raises ProvenanceValidationError if any check fails.
        """
        if not memory.conversation_id:
            raise ProvenanceValidationError("StructuredMemory must have a non-empty conversation_id.")

        if memory.start_msg_index > memory.end_msg_index:
            raise ProvenanceValidationError(
                f"Invalid index range: start_msg_index ({memory.start_msg_index}) "
                f"cannot be greater than end_msg_index ({memory.end_msg_index})."
            )

        if not memory.source_message_ids:
            raise ProvenanceValidationError("StructuredMemory must have at least one source_message_id.")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Verify parent conversation exists
            cursor.execute("SELECT id FROM conversations WHERE id = ?", (memory.conversation_id,))
            if not cursor.fetchone():
                raise ProvenanceValidationError(
                    f"Referenced conversation '{memory.conversation_id}' does not exist."
                )

            # 2. Fetch raw messages in the declared index range for this conversation
            cursor.execute(
                """
                SELECT id, msg_index, conversation_id FROM messages 
                WHERE conversation_id = ? AND msg_index BETWEEN ? AND ?
                ORDER BY msg_index ASC
                """,
                (memory.conversation_id, memory.start_msg_index, memory.end_msg_index),
            )
            range_rows = cursor.fetchall()
            range_msg_ids = [r["id"] for r in range_rows]

            if not range_rows:
                raise ProvenanceValidationError(
                    f"No messages found for conversation '{memory.conversation_id}' "
                    f"in range [{memory.start_msg_index}, {memory.end_msg_index}]."
                )

            # 3. Check for exact match between source_message_ids and the range's message IDs
            for msg_id in memory.source_message_ids:
                if msg_id not in range_msg_ids:
                    # Check if message belongs to another conversation or doesn't exist
                    cursor.execute("SELECT conversation_id, msg_index FROM messages WHERE id = ?", (msg_id,))
                    other_row = cursor.fetchone()
                    if other_row:
                        raise ProvenanceValidationError(
                            f"Message '{msg_id}' belongs to conversation '{other_row['conversation_id']}' "
                            f"(msg_index={other_row['msg_index']}), not target conversation "
                            f"'{memory.conversation_id}' in range [{memory.start_msg_index}, {memory.end_msg_index}]."
                        )
                    else:
                        raise ProvenanceValidationError(
                            f"Referenced message '{msg_id}' does not exist in the database."
                        )

            if len(memory.source_message_ids) != len(range_rows):
                raise ProvenanceValidationError(
                    f"Count mismatch: source_message_ids has {len(memory.source_message_ids)} items, "
                    f"but range [{memory.start_msg_index}, {memory.end_msg_index}] contains {len(range_rows)} messages."
                )

        return True

    def save_memory(self, memory: StructuredMemory, validate: bool = True) -> str:
        """
        Validates provenance and persists a StructuredMemory to the database.
        Returns the memory ID.
        """
        if validate:
            self.validate_provenance(memory)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            source_ids_json = json.dumps(memory.source_message_ids)

            cursor.execute(
                """
                INSERT OR REPLACE INTO structured_memories
                (id, conversation_id, memory_type, content, start_msg_index, end_msg_index, 
                 source_message_ids, provider, confidence, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    memory.conversation_id,
                    memory.memory_type,
                    memory.content,
                    memory.start_msg_index,
                    memory.end_msg_index,
                    source_ids_json,
                    memory.provider,
                    memory.confidence,
                    memory.status,
                    memory.created_at,
                    memory.updated_at,
                ),
            )
            conn.commit()

        return memory.id

    def get_memory(self, memory_id: str) -> Optional[StructuredMemory]:
        """
        Retrieves a StructuredMemory by its ID. Returns None if not found.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM structured_memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_memory(row)

    def list_memories_for_conversation(
        self,
        conversation_id: str,
        memory_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[StructuredMemory]:
        """
        Lists all structured memories for a conversation, optionally filtered by memory_type and status.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM structured_memories WHERE conversation_id = ?"
            params = [conversation_id]

            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY start_msg_index ASC, created_at ASC"

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_memory(r) for r in rows]

    def delete_memory(self, memory_id: str) -> bool:
        """
        Deletes a single structured memory by ID.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM structured_memories WHERE id = ?", (memory_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    def resolve_provenance_messages(self, memory: StructuredMemory) -> List[Message]:
        """
        Resolves and returns the full raw Message objects that back this structured memory.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND msg_index BETWEEN ? AND ?
                ORDER BY msg_index ASC
                """,
                (memory.conversation_id, memory.start_msg_index, memory.end_msg_index),
            )
            rows = cursor.fetchall()
            return [
                Message(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    role=r["role"],
                    content=r["content"],
                    index=r["msg_index"],
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    def _row_to_memory(self, row: Any) -> StructuredMemory:
        """Helper to convert a SQLite row to a StructuredMemory dataclass instance."""
        source_ids = json.loads(row["source_message_ids"]) if row["source_message_ids"] else []
        return StructuredMemory(
            id=row["id"],
            conversation_id=row["conversation_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            start_msg_index=row["start_msg_index"],
            end_msg_index=row["end_msg_index"],
            source_message_ids=source_ids,
            provider=row["provider"],
            confidence=float(row["confidence"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
