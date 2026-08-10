"""
Database connection manager and schema initialization module using SQLite.

Handles both file-based SQLite databases and persistent in-memory databases for testing.
Adds message_embeddings table for storing semantic vector representations.
"""

import sqlite3
import os
from typing import Optional

DEFAULT_DB_PATH = os.path.join("data", "memory.db")


class Database:
    """
    Manages SQLite database connections and table creation.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._memory_conn: Optional[sqlite3.Connection] = None

        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON;")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates and returns a SQLite connection with foreign keys enabled.
        """
        if self.db_path == ":memory:":
            return self._memory_conn

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        """
        Creates conversations, messages, and message_embeddings tables if they do not exist.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'Unknown',
                imported_at TEXT NOT NULL,
                original_date TEXT,
                category TEXT,
                tags TEXT DEFAULT '',
                description TEXT
            );
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                msg_index INTEGER NOT NULL,
                timestamp TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
            );
        """)

        # Message Embeddings table for Semantic Vector Search
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_embeddings (
                message_id TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                model_name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
            );
        """)

        # Create indices for quick lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
            ON messages(conversation_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_imported_at 
            ON conversations(imported_at DESC);
        """)

        conn.commit()

        if self.db_path != ":memory:":
            conn.close()
