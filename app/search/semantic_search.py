"""
Semantic Search Engine and Embedding Vectorization module.

Computes dense vector representations for queries and messages, computes
Cosine Similarity, and persists embeddings in SQLite.
"""

import json
import math
import re
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository


class LocalVectorEngine:
    """
    Lightweight, zero-dependency Semantic Vectorizer.
    Generates normalized term & n-gram frequency vectors for semantic similarity.
    Fallback when external sentence-transformers model is not installed.
    """

    @staticmethod
    def get_vector(text: str) -> Dict[str, float]:
        if not text:
            return {}

        clean_text = text.lower()
        words = re.findall(r'\w+', clean_text)
        
        counts: Dict[str, float] = {}

        # 1-gram word frequencies
        for w in words:
            if len(w) > 1:
                counts[w] = counts.get(w, 0.0) + 1.0

        # 2-gram word pairs for phrase semantics
        for i in range(len(words) - 1):
            phrase = f"{words[i]}_{words[i+1]}"
            counts[phrase] = counts.get(phrase, 0.0) + 1.5

        # Character 3-grams for morphological similarity
        for w in words:
            if len(w) >= 3:
                for i in range(len(w) - 2):
                    tri = f"char_{w[i:i+3]}"
                    counts[tri] = counts.get(tri, 0.0) + 0.3

        # L2 Vector Normalization
        magnitude = math.sqrt(sum(v * v for v in counts.values()))
        if magnitude == 0:
            return {}

        return {k: v / magnitude for k, v in counts.items()}

    @staticmethod
    def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        if not vec1 or not vec2:
            return 0.0

        # Dot product of normalized sparse/dense vectors
        dot = 0.0
        # Iterate over smaller dict
        if len(vec1) > len(vec2):
            vec1, vec2 = vec2, vec1

        for k, val in vec1.items():
            if k in vec2:
                dot += val * vec2[k]

        return min(1.0, max(0.0, dot))


class SemanticSearchEngine:
    """
    Manages embedding generation, storage, and semantic vector similarity search.
    """

    def __init__(self, repo: Optional[ConversationRepository] = None):
        self.repo = repo or ConversationRepository()
        self.db = self.repo.db
        self.vector_engine = LocalVectorEngine()

    def generate_embedding(self, text: str) -> Dict[str, float]:
        """
        Generates embedding dictionary vector for given text.
        """
        return self.vector_engine.get_vector(text)

    def index_conversation_messages(self, conversation_id: str):
        """
        Generates and stores embeddings for all messages in a conversation.
        """
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            return

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            for msg in conv.messages:
                # Combine title, role, content, category, tags for rich semantic vector context
                context_text = f"{conv.title} {conv.category or ''} {' '.join(conv.tags)} {msg.role}: {msg.content}"
                vector = self.generate_embedding(context_text)
                vec_json = json.dumps(vector)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO message_embeddings
                    (message_id, embedding_json, model_name, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (msg.id, vec_json, "local-vector-v1", now),
                )
            conn.commit()

    def search_semantic(self, query: str, limit: int = 50) -> List[Tuple[str, float]]:
        """
        Performs semantic similarity search for a query across all stored message embeddings.

        Returns:
            List of (message_id, cosine_similarity_score) sorted by similarity DESC.
        """
        if not query or not query.strip():
            return []

        query_vec = self.generate_embedding(query)
        if not query_vec:
            return []

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message_id, embedding_json FROM message_embeddings")
            rows = cursor.fetchall()

        scores: List[Tuple[str, float]] = []
        for row in rows:
            msg_id = row["message_id"]
            try:
                msg_vec = json.loads(row["embedding_json"])
                sim = self.vector_engine.cosine_similarity(query_vec, msg_vec)
                if sim > 0.0:
                    scores.append((msg_id, sim))
            except Exception:
                continue

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:limit]
