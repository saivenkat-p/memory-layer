"""
Real Neural Semantic Search Engine using local SentenceTransformers.

Uses pretrained model 'all-MiniLM-L6-v2' (384 dimensions) to compute 
dense vector embeddings and exact Cosine Similarity across stored message embeddings.
"""

import json
import math
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository


class NeuralEmbeddingEncoder:
    """
    Singleton wrapper for SentenceTransformer model ('all-MiniLM-L6-v2').
    Runs 100% locally on CPU without sending data to external APIs.
    """
    _instance = None

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2"):
        if cls._instance is None:
            from sentence_transformers import SentenceTransformer
            cls._instance = super(NeuralEmbeddingEncoder, cls).__new__(cls)
            cls._instance.model_name = model_name
            # Load pretrained SentenceTransformer model locally
            cls._instance.model = SentenceTransformer(model_name)
        return cls._instance

    def encode(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * 384
        vec = self.model.encode(text, convert_to_numpy=True)
        # Normalize vector for cosine dot product
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


class SemanticSearchEngine:
    """
    Manages neural embedding generation, SQLite persistence, and vector cosine similarity search.
    """

    def __init__(self, repo: Optional[ConversationRepository] = None, model_name: str = "all-MiniLM-L6-v2"):
        self.repo = repo or ConversationRepository()
        self.db = self.repo.db
        self.model_name = model_name
        self.encoder = NeuralEmbeddingEncoder(model_name)

    def generate_embedding(self, text: str) -> List[float]:
        return self.encoder.encode(text)

    def index_conversation_messages(self, conversation_id: str):
        """
        Generates and stores 384-dimensional dense neural embeddings for all messages in a conversation.
        """
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            for msg in conv.messages:
                # Construct rich semantic context string
                context_text = f"{conv.title}. {conv.category or ''} {' '.join(conv.tags)}. {msg.content}"
                vector = self.generate_embedding(context_text)
                vec_json = json.dumps(vector)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO message_embeddings
                    (message_id, embedding_json, model_name, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (msg.id, vec_json, self.model_name, now),
                )
            conn.commit()

    def search_semantic(self, query: str, limit: int = 50) -> List[Tuple[str, float]]:
        """
        Performs vector similarity search for a query across all stored message embeddings.

        Returns:
            List of (message_id, cosine_similarity_score) sorted by similarity DESC.
        """
        if not query or not query.strip():
            return []

        query_vec = np.array(self.generate_embedding(query), dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm == 0:
            return []

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message_id, embedding_json FROM message_embeddings")
            rows = cursor.fetchall()

        scores: List[Tuple[str, float]] = []

        for row in rows:
            msg_id = row["message_id"]
            try:
                msg_vec = np.array(json.loads(row["embedding_json"]), dtype=np.float32)
                # Dot product of normalized vectors equals Cosine Similarity
                sim = float(np.dot(query_vec, msg_vec))
                sim_clamped = min(1.0, max(0.0, sim))
                scores.append((msg_id, sim_clamped))
            except Exception:
                continue

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:limit]
