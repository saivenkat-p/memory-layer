"""
Neural Semantic Search Engine

Uses a local SentenceTransformer model to generate semantic embeddings.

Features:
- Local embedding generation
- Model/version awareness
- Embedding dimension validation
- Stale embedding detection
- Persistent SQLite embeddings
- Semantic similarity search
- Re-indexing support
- Explicit error reporting

Active model:
    all-MiniLM-L6-v2

Embedding dimension:
    384
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


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

ACTIVE_MODEL_NAME = "all-MiniLM-L6-v2"
EXPECTED_DIMENSION = 384

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Neural Embedding Encoder
# ---------------------------------------------------------------------

class NeuralEmbeddingEncoder:
    """
    Wrapper around SentenceTransformer.

    The model runs locally on CPU.
    Conversation data is not sent to an external embedding API.
    """

    def __init__(
        self,
        model_name: str = ACTIVE_MODEL_NAME,
    ):
        self.model_name = model_name
        self.model = None

        self._init_model()

    # -----------------------------------------------------------------
    # Model initialization
    # -----------------------------------------------------------------

    def _init_model(self):
        """
        Load the SentenceTransformer model once.

        Also validates that the model produces the expected
        embedding dimension.
        """

        if self.model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is not installed.\n"
                "Install it using:\n"
                "python -m pip install sentence-transformers"
            ) from e

        try:
            logger.info(
                "Loading SentenceTransformer model '%s'...",
                self.model_name,
            )

            self.model = SentenceTransformer(
                self.model_name,
                device="cpu",
            )

            dimension = (
                self.model.get_sentence_embedding_dimension()
            )

            if dimension != EXPECTED_DIMENSION:
                raise RuntimeError(
                    "Embedding dimension mismatch. "
                    f"Expected {EXPECTED_DIMENSION}, "
                    f"but model produced {dimension}."
                )

            logger.info(
                "Model '%s' loaded successfully. "
                "Embedding dimension: %s",
                self.model_name,
                dimension,
            )

        except Exception as e:
            self.model = None

            logger.exception(
                "Failed to load embedding model '%s'.",
                self.model_name,
            )

            raise RuntimeError(
                f"Could not load embedding model "
                f"'{self.model_name}'. "
                f"Original error: {e}"
            ) from e

    # -----------------------------------------------------------------
    # Generate embedding
    # -----------------------------------------------------------------

    def encode(self, text: str) -> List[float]:
        """
        Convert text into a normalized 384-dimensional embedding.
        """

        if not text or not text.strip():
            return [0.0] * EXPECTED_DIMENSION

        if self.model is None:
            self._init_model()

        try:
            vector = self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

            vector = np.asarray(
                vector,
                dtype=np.float32,
            )

            # Make sure the vector is one-dimensional.
            if vector.ndim != 1:
                raise RuntimeError(
                    f"Expected a 1D embedding vector, "
                    f"got shape {vector.shape}."
                )

            # Validate dimension.
            if len(vector) != EXPECTED_DIMENSION:
                raise RuntimeError(
                    "Embedding dimension mismatch. "
                    f"Expected {EXPECTED_DIMENSION}, "
                    f"got {len(vector)}."
                )

            # Check for NaN / infinity.
            if not np.all(np.isfinite(vector)):
                raise RuntimeError(
                    "Embedding contains invalid numeric values."
                )

            # Normalize vector.
            norm = float(np.linalg.norm(vector))

            if not math.isfinite(norm):
                raise RuntimeError(
                    "Embedding norm is invalid."
                )

            if norm > 0:
                vector = vector / norm

            return vector.tolist()

        except Exception as e:
            logger.exception(
                "Error encoding text with model '%s'.",
                self.model_name,
            )

            raise RuntimeError(
                f"Embedding encoding failed: {e}"
            ) from e


# ---------------------------------------------------------------------
# Semantic Search Engine
# ---------------------------------------------------------------------

class SemanticSearchEngine:
    """
    Handles:

    1. Embedding generation
    2. Embedding persistence
    3. Stale embedding detection
    4. Semantic similarity search
    5. Re-indexing
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        model_name: str = ACTIVE_MODEL_NAME,
    ):
        self.repo = repo or ConversationRepository()

        self.db = self.repo.db

        self.model_name = model_name

        self.encoder = NeuralEmbeddingEncoder(
            model_name=model_name
        )

    # -----------------------------------------------------------------
    # Generate embedding
    # -----------------------------------------------------------------

    def generate_embedding(
        self,
        text: str,
    ) -> List[float]:
        """
        Generate an embedding using the active model.
        """

        return self.encoder.encode(text)

    # -----------------------------------------------------------------
    # Validate embedding
    # -----------------------------------------------------------------

    def _validate_embedding(
        self,
        embedding: Any,
    ) -> bool:
        """
        Validate an embedding before using it.
        """

        if embedding is None:
            return False

        try:
            vector = np.asarray(
                embedding,
                dtype=np.float32,
            )

            if vector.ndim != 1:
                return False

            if len(vector) != EXPECTED_DIMENSION:
                return False

            if not np.all(np.isfinite(vector)):
                return False

            norm = np.linalg.norm(vector)

            if norm == 0:
                return False

            return True

        except Exception:
            return False

    # -----------------------------------------------------------------
    # Cosine similarity
    # -----------------------------------------------------------------

    def _cosine_similarity(
        self,
        vector_a: List[float],
        vector_b: List[float],
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Since embeddings are normalized, this is effectively
        their dot product.
        """

        if not self._validate_embedding(vector_a):
            return 0.0

        if not self._validate_embedding(vector_b):
            return 0.0

        a = np.asarray(
            vector_a,
            dtype=np.float32,
        )

        b = np.asarray(
            vector_b,
            dtype=np.float32,
        )

        similarity = float(
            np.dot(a, b)
        )

        # Keep numerical noise inside [-1, 1].
        return max(
            -1.0,
            min(1.0, similarity),
        )

    # -----------------------------------------------------------------
    # Index conversation
    # -----------------------------------------------------------------

    def index_conversation_messages(
        self,
        conversation_id: str,
    ) -> int:
        """
        Generate and store embeddings for every message
        in a conversation.

        Returns the number of successfully indexed messages.
        """

        conversation = self.repo.get_conversation(
            conversation_id
        )

        if not conversation:
            logger.warning(
                "Conversation not found: %s",
                conversation_id,
            )

            return 0

        indexed_count = 0

        for message in conversation.messages:

            if not message.content:
                continue

            try:
                embedding = self.generate_embedding(
                    message.content
                )

                if not self._validate_embedding(
                    embedding
                ):
                    logger.error(
                        "Invalid embedding generated "
                        "for message %s",
                        message.id,
                    )

                    continue

                embedding_json = json.dumps(
                    embedding
                )

                self._save_embedding(
                    message_id=message.id,
                    embedding_json=embedding_json,
                )

                indexed_count += 1

            except Exception as e:
                logger.error(
                    "Failed to index message %s: %s",
                    message.id,
                    e,
                )

        return indexed_count

    # -----------------------------------------------------------------
    # Save embedding
    # -----------------------------------------------------------------

    def _save_embedding(
        self,
        message_id: str,
        embedding_json: str,
    ):
        """
        Persist an embedding in SQLite.
        """

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        query = """
        INSERT OR REPLACE INTO message_embeddings
        (
            message_id,
            embedding_json,
            model_name,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        """

        self.db.execute(
            query,
            (
                message_id,
                embedding_json,
                self.model_name,
                timestamp,
            ),
        )

        self.db.commit()

    # -----------------------------------------------------------------
    # Check embedding compatibility
    # -----------------------------------------------------------------

    def _is_compatible_embedding(
        self,
        model_name: Optional[str],
        embedding: Any,
    ) -> bool:
        """
        Determine whether a stored embedding can be used
        by the current semantic search engine.
        """

        if model_name != self.model_name:
            return False

        return self._validate_embedding(
            embedding
        )

    # -----------------------------------------------------------------
    # Semantic search
    # -----------------------------------------------------------------

    def search_semantic(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.30,
    ) -> List[Dict[str, Any]]:
        """
        Search memories using semantic similarity.

        Returns the highest-scoring compatible embeddings.
        """

        if not query or not query.strip():
            return []

        query_embedding = self.generate_embedding(
            query
        )

        rows = self.db.fetch_all(
            """
            SELECT
                me.message_id,
                me.embedding_json,
                me.model_name,
                m.content,
                m.role,
                m.message_index,
                c.id AS conversation_id,
                c.title,
                c.source
            FROM message_embeddings me
            JOIN messages m
                ON m.id = me.message_id
            JOIN conversations c
                ON c.id = m.conversation_id
            """
        )

        results = []

        for row in rows:

            stored_model = row["model_name"]

            # Ignore embeddings from old models.
            if stored_model != self.model_name:
                logger.debug(
                    "Skipping stale embedding for "
                    "message %s. Stored model=%s, "
                    "active model=%s",
                    row["message_id"],
                    stored_model,
                    self.model_name,
                )

                continue

            try:
                embedding = json.loads(
                    row["embedding_json"]
                )

            except (TypeError, json.JSONDecodeError):
                logger.warning(
                    "Invalid JSON embedding for message %s",
                    row["message_id"],
                )

                continue

            if not self._validate_embedding(
                embedding
            ):
                logger.warning(
                    "Invalid embedding for message %s",
                    row["message_id"],
                )

                continue

            similarity = self._cosine_similarity(
                query_embedding,
                embedding,
            )

            if similarity < threshold:
                continue

            results.append(
                {
                    "message_id": row["message_id"],
                    "conversation_id": row[
                        "conversation_id"
                    ],
                    "title": row["title"],
                    "source": row["source"],
                    "role": row["role"],
                    "message_index": row[
                        "message_index"
                    ],
                    "content": row["content"],
                    "similarity": similarity,
                    "score": similarity,
                }
            )

        results.sort(
            key=lambda x: x["similarity"],
            reverse=True,
        )

        return results[:top_k]

    # -----------------------------------------------------------------
    # Re-index all conversations
    # -----------------------------------------------------------------

    def reindex_all_embeddings(self) -> Dict[str, int]:
        """
        Regenerate embeddings for every stored conversation.

        Existing conversation/message data is preserved.
        Only embeddings are replaced.
        """

        conversations = self.repo.list_conversations()

        total_messages = 0
        indexed_messages = 0
        failed_messages = 0

        for conversation in conversations:

            for message in conversation.messages:

                total_messages += 1

                if not message.content:
                    continue

                try:
                    embedding = self.generate_embedding(
                        message.content
                    )

                    if not self._validate_embedding(
                        embedding
                    ):
                        failed_messages += 1

                        logger.error(
                            "Invalid embedding for "
                            "message %s",
                            message.id,
                        )

                        continue

                    self._save_embedding(
                        message_id=message.id,
                        embedding_json=json.dumps(
                            embedding
                        ),
                    )

                    indexed_messages += 1

                except Exception as e:
                    failed_messages += 1

                    logger.error(
                        "Failed to embed message %s: %s",
                        message.id,
                        e,
                    )

        return {
            "total_messages": total_messages,
            "indexed_messages": indexed_messages,
            "failed_messages": failed_messages,
        }

    # -----------------------------------------------------------------
    # Get embedding statistics
    # -----------------------------------------------------------------

    def get_embedding_statistics(
        self,
    ) -> Dict[str, int]:
        """
        Return basic statistics about stored embeddings.
        """

        total = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM message_embeddings
            """
        )

        active = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM message_embeddings
            WHERE model_name = ?
            """,
            (self.model_name,),
        )

        stale = self.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM message_embeddings
            WHERE model_name != ?
            """,
            (self.model_name,),
        )

        return {
            "total_embeddings": (
                total["count"] if total else 0
            ),
            "active_embeddings": (
                active["count"] if active else 0
            ),
            "stale_embeddings": (
                stale["count"] if stale else 0
            ),
        }