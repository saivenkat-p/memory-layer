"""
Real Neural Semantic Search Engine using local SentenceTransformers.

Features embedding version/model awareness, stale embedding detection,
robust validation, explicit error reporting, and re-indexing capabilities.
Uses thread-safe lazy model caching to prevent singleton initialization errors.
"""

import os
import sys

# Disable tqdm progress bars and HF warnings before importing transformers/sentence_transformers
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import json
import math
import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository

ACTIVE_MODEL_NAME = "all-MiniLM-L6-v2"
EXPECTED_DIMENSION = 384

logger = logging.getLogger(__name__)

# Global model cache to safely reuse SentenceTransformer instances
_MODEL_CACHE: Dict[str, Any] = {}


def get_sentence_transformer_model(model_name: str = ACTIVE_MODEL_NAME):
    """
    Safely loads and caches SentenceTransformer model weights.
    Prevents duplicate memory loading and incomplete object states.
    """
    if model_name not in _MODEL_CACHE:
        try:
            import transformers
            transformers.logging.set_verbosity_error()
        except Exception:
            pass

        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading SentenceTransformer model '{model_name}' into memory...")
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


class NeuralEmbeddingEncoder:
    """
    Encoder wrapper for SentenceTransformer model ('all-MiniLM-L6-v2').
    Runs 100% locally on CPU without sending data to external APIs.
    """

    def __init__(self, model_name: str = ACTIVE_MODEL_NAME):
        self.model_name = model_name

    @property
    def model(self):
        """Lazy property returning cached SentenceTransformer instance."""
        return get_sentence_transformer_model(self.model_name)

    def encode(self, text: str) -> List[float]:
        """Encodes text string into a 384-dimensional normalized float list."""
        if not text or not text.strip():
            return [0.0] * EXPECTED_DIMENSION
        try:
            model = self.model
            vec = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            return vec.tolist()
        except Exception as e:
            logger.error(f"Error encoding text with model {self.model_name}: {e}")
            raise RuntimeError(f"Embedding encoding failed: {e}")


class SemanticSearchEngine:
    """
    Manages neural embedding generation, SQLite persistence, stale vector detection,
    and cosine similarity search.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        model_name: str = ACTIVE_MODEL_NAME,
    ):
        self.repo = repo or ConversationRepository()
        self.db = self.repo.db
        self.model_name = model_name
        self.encoder = NeuralEmbeddingEncoder(model_name)

    def generate_embedding(self, text: str) -> List[float]:
        """Generates embedding for text using the active model."""
        return self.encoder.encode(text)

    def index_conversation_messages(self, conversation_id: str) -> int:
        """
        Generates and stores 384-dimensional dense neural embeddings for all messages in a conversation.
        Returns the number of messages successfully indexed.
        """
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            return 0

        indexed_count = 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            for msg in conv.messages:
                context_text = f"{conv.title}. {conv.category or ''} {' '.join(conv.tags)}. {msg.content}"
                vector = self.generate_embedding(context_text)
                
                if not self.validate_vector_list(vector):
                    raise ValueError(f"Generated vector for message {msg.id} is invalid.")

                vec_json = json.dumps(vector)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO message_embeddings
                    (message_id, embedding_json, model_name, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (msg.id, vec_json, self.model_name, now),
                )
                indexed_count += 1

            conn.commit()

        return indexed_count

    def validate_vector_list(self, vec: List[float]) -> bool:
        """Validates vector dimensions, float types, finite values, and non-zero norm."""
        if not isinstance(vec, list) or len(vec) != EXPECTED_DIMENSION:
            return False
        for val in vec:
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                return False
        norm = math.sqrt(sum(x * x for x in vec))
        return norm > 0.0

    def validate_stored_embedding(
        self, embedding_json: str, stored_model_name: str
    ) -> Tuple[bool, str, Optional[np.ndarray]]:
        """
        Validates stored embedding row against active model and schema.

        Returns:
            Tuple of (is_valid, reason_message, numpy_vector)
        """
        if stored_model_name != self.model_name:
            return False, f"Stale model name '{stored_model_name}' (active: '{self.model_name}')", None

        try:
            vec_list = json.loads(embedding_json)
        except Exception as e:
            return False, f"JSON parse failure: {e}", None

        if not self.validate_vector_list(vec_list):
            return False, "Invalid vector dimensions, infinite values, or zero norm", None

        return True, "Valid", np.array(vec_list, dtype=np.float32)

    def reindex_all_embeddings(self) -> Dict[str, Any]:
        """
        Reindexes all conversations and messages stored in the database using the CURRENT active embedding model.
        Replaces any stale or incompatible embeddings.

        Returns summary stats dict.
        """
        conversations = self.repo.list_conversations(limit=1000)
        total_convs = len(conversations)
        total_messages = sum(c.message_count for c in conversations)
        reindexed_count = 0
        failures_count = 0

        for conv in conversations:
            try:
                count = self.index_conversation_messages(conv.id)
                reindexed_count += count
            except Exception as e:
                logger.error(f"Failed to reindex conversation '{conv.title}' ({conv.id}): {e}")
                failures_count += conv.message_count

        return {
            "model_name": self.model_name,
            "conversations_found": total_convs,
            "messages_found": total_messages,
            "embeddings_reindexed": reindexed_count,
            "failures": failures_count,
        }

    def search_semantic(self, query: str, limit: int = 50) -> List[Tuple[str, float]]:
        """
        Performs vector similarity search for a query across stored message embeddings.
        Detects and skips stale/incompatible embeddings with logged reasons.
        """
        if not query or not query.strip():
            return []

        query_vec = np.array(self.generate_embedding(query), dtype=np.float32)
        norm = float(np.linalg.norm(query_vec))
        if norm == 0:
            return []

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message_id, embedding_json, model_name FROM message_embeddings")
            rows = cursor.fetchall()

        scores: List[Tuple[str, float]] = []
        stale_count = 0

        for row in rows:
            msg_id = row["message_id"]
            stored_json = row["embedding_json"]
            stored_model = row["model_name"]

            is_valid, reason, msg_vec = self.validate_stored_embedding(stored_json, stored_model)
            if not is_valid:
                stale_count += 1
                logger.debug(f"Skipping embedding for message {msg_id}: {reason}")
                continue

            sim = float(np.dot(query_vec, msg_vec))
            sim_clamped = min(1.0, max(0.0, sim))
            scores.append((msg_id, sim_clamped))

        if stale_count > 0:
            logger.warning(
                f"Encountered {stale_count} stale/incompatible embedding(s) during search. "
                f"Run reindex_embeddings.py to update them to '{self.model_name}'."
            )

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:limit]
