"""
Real Neural Semantic Search Engine using local SentenceTransformers.

Features embedding version/model awareness, stale embedding detection,
robust validation, explicit error reporting, and re-indexing capabilities.
"""

import sys
import os

# Disable progress bars and HF warnings
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Fix Windows Streamlit sys.stderr.flush OSError [Errno 22] bug during tqdm output
class SafeStreamWrapper:
    def __init__(self, original_stream):
        self._original = original_stream

    def write(self, s):
        try:
            return self._original.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            if hasattr(self._original, "flush"):
                return self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)

if sys.stderr is not None and not getattr(sys.stderr, "_is_safe_wrapper", False):
    sys.stderr = SafeStreamWrapper(sys.stderr)
    sys.stderr._is_safe_wrapper = True

if sys.stdout is not None and not getattr(sys.stdout, "_is_safe_wrapper", False):
    sys.stdout = SafeStreamWrapper(sys.stdout)
    sys.stdout._is_safe_wrapper = True

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


class NeuralEmbeddingEncoder:
    """
    Encoder wrapper for SentenceTransformer model ('all-MiniLM-L6-v2').
    Runs 100% locally on CPU without sending data to external APIs.
    """

    def __init__(self, model_name: str = ACTIVE_MODEL_NAME):
        self.model_name = model_name
        self.model = None
        self._init_model()

    def _init_model(self):
        if self.model is None:
            try:
                import transformers
                transformers.logging.set_verbosity_error()
            except Exception:
                pass
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer model '{self.model_name}' into memory...")
            try:
                # Prefer locally cached model weights to avoid HuggingFace Hub network hiccups
                self.model = SentenceTransformer(self.model_name, device="cpu", local_files_only=True)
            except Exception:
                # Fallback if local_files_only is unsupported or cache is fresh
                self.model = SentenceTransformer(self.model_name, device="cpu")

    def encode(self, text: str) -> List[float]:
        """Encodes text string into a 384-dimensional normalized float list."""
        if not text or not text.strip():
            return [0.0] * EXPECTED_DIMENSION

        if not hasattr(self, "model") or self.model is None:
            self._init_model()

        try:
            vec = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            vec = np.asarray(vec, dtype=np.float32)

            if vec.ndim != 1 or len(vec) != EXPECTED_DIMENSION:
                raise RuntimeError(f"Unexpected embedding shape: {vec.shape}")

            if not np.all(np.isfinite(vec)):
                raise RuntimeError("Embedding vector contains non-finite values.")

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

    def _validate_embedding(self, embedding: Any) -> bool:
        """Validates vector dimensions, float types, finite values, and non-zero norm."""
        if not isinstance(embedding, list) or len(embedding) != EXPECTED_DIMENSION:
            return False
        for val in embedding:
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                return False
        norm = math.sqrt(sum(x * x for x in embedding))
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

        if not self._validate_embedding(vec_list):
            return False, "Invalid vector dimensions, infinite values, or zero norm", None

        return True, "Valid", np.array(vec_list, dtype=np.float32)

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
                if not msg.content or not msg.content.strip():
                    continue
                context_text = f"{conv.title}. {conv.category or ''} {' '.join(conv.tags)}. {msg.content}"
                vector = self.generate_embedding(context_text)

                if not self._validate_embedding(vector):
                    logger.error(f"Invalid vector generated for message {msg.id}")
                    continue

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

    def search_semantic(
        self,
        query: str,
        limit: int = 50,
        top_k: Optional[int] = None,
        threshold: float = 0.0,
    ) -> List[Tuple[str, float]]:
        """
        Performs vector similarity search for a query across stored message embeddings.
        Detects and skips stale/incompatible embeddings with logged reasons.
        """
        max_results = top_k if top_k is not None else limit
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
            if sim_clamped >= threshold:
                scores.append((msg_id, sim_clamped))

        if stale_count > 0:
            logger.warning(
                f"Encountered {stale_count} stale/incompatible embedding(s) during search. "
                f"Run reindex_embeddings.py to update them to '{self.model_name}'."
            )

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:max_results]

    def get_embedding_statistics(self) -> Dict[str, int]:
        """Returns statistics about stored embeddings."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS count FROM message_embeddings")
            total = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) AS count FROM message_embeddings WHERE model_name = ?", (self.model_name,))
            active = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) AS count FROM message_embeddings WHERE model_name != ?", (self.model_name,))
            stale = cursor.fetchone()["count"]

            return {
                "total_embeddings": total,
                "active_embeddings": active,
                "stale_embeddings": stale,
            }