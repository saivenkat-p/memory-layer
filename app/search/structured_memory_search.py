"""
Structured Memory Search Engine & Provenance Hydration (Milestone V6.5-E4).

Provides dedicated hybrid search, filtering, and provenance resolution over
persisted StructuredMemory records without requiring live LLM calls during search.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
import sqlite3

from app.models.schemas import StructuredMemory, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.structured_memory_repository import StructuredMemoryRepository

logger = logging.getLogger(__name__)

# Optional local neural embedding support
try:
    from sentence_transformers import SentenceTransformer, util
    _EMBEDDING_MODEL: Optional[SentenceTransformer] = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    logger.warning(f"sentence_transformers unavailable for structured memory search ({e}). Using lexical fallback.")
    _EMBEDDING_MODEL = None


@dataclass
class StructuredMemorySearchResult:
    """
    Encapsulates a ranked search result over a StructuredMemory record.
    """
    memory: StructuredMemory
    score: float
    match_type: str = "hybrid"  # 'hybrid', 'keyword', 'semantic', 'exact'
    matched_terms: List[str] = field(default_factory=list)
    source_messages: List[Message] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "matched_terms": self.matched_terms,
            "source_messages": [m.to_dict() for m in self.source_messages],
        }


class StructuredMemorySearchEngine:
    """
    Search engine specialized for StructuredMemory records.
    Supports multi-attribute filtering (memory_type, status, conversation_id),
    hybrid lexical/semantic relevance scoring, and complete provenance hydration.
    """

    def __init__(
        self,
        memory_repo: Optional[StructuredMemoryRepository] = None,
        conv_repo: Optional[ConversationRepository] = None,
        db: Optional[Database] = None,
    ):
        self.db = db or Database()
        self.memory_repo = memory_repo or StructuredMemoryRepository(db=self.db)
        self.conv_repo = conv_repo or ConversationRepository(db=self.db)

    def list_memories(
        self,
        memory_type: Optional[str] = None,
        conversation_id: Optional[str] = None,
        status: Optional[str] = "active",
        limit: int = 50,
        offset: int = 0,
        hydrate_provenance: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Lists stored structured memories matching given filters with pagination.
        Returns (list_of_memory_dicts, total_count).
        """
        where_clauses = []
        params: List[Any] = []

        if conversation_id:
            where_clauses.append("conversation_id = ?")
            params.append(conversation_id)

        if memory_type:
            where_clauses.append("memory_type = ?")
            params.append(memory_type)

        if status and status.lower() != "all":
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Count total matching
            count_query = f"SELECT COUNT(*) FROM structured_memories{where_sql}"
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()[0]

            # Fetch page
            query = f"""
                SELECT * FROM structured_memories{where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, tuple(params + [limit, offset]))
            rows = cursor.fetchall()

        memories: List[Dict[str, Any]] = []
        for r in rows:
            mem = self.memory_repo._row_to_memory(r)
            mem_dict = mem.to_dict()
            if hydrate_provenance:
                source_msgs = self.memory_repo.resolve_provenance_messages(mem)
                mem_dict["source_messages"] = [m.to_dict() for m in source_msgs]
            memories.append(mem_dict)

        return memories, total_count

    def get_memory_with_provenance(
        self,
        memory_id: str,
        hydrate_provenance: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single StructuredMemory by ID with optional hydrated source messages.
        """
        memory = self.memory_repo.get_memory(memory_id)
        if not memory:
            return None

        mem_dict = memory.to_dict()
        if hydrate_provenance:
            source_msgs = self.memory_repo.resolve_provenance_messages(memory)
            mem_dict["source_messages"] = [m.to_dict() for m in source_msgs]

        return mem_dict

    def search_memories(
        self,
        query: str,
        memory_type: Optional[str] = None,
        conversation_id: Optional[str] = None,
        status: Optional[str] = "active",
        limit: int = 20,
        threshold: float = 0.35,
        hydrate_provenance: bool = True,
    ) -> List[StructuredMemorySearchResult]:
        """
        Searches StructuredMemory records using hybrid lexical & neural scoring.
        Applies type/status/conversation filters, filters by relevance threshold,
        and returns ranked results with hydrated provenance messages.
        """
        query_str = query.strip()
        if not query_str:
            return []

        # 1. Fetch candidate pool matching structural filters
        candidates_raw, _ = self.list_memories(
            memory_type=memory_type,
            conversation_id=conversation_id,
            status=status,
            limit=500,  # Fetch broad candidate pool for in-memory scoring
            offset=0,
            hydrate_provenance=False,
        )

        if not candidates_raw:
            return []

        # Convert raw dicts back to StructuredMemory instances
        candidate_memories = [
            StructuredMemory(
                id=c["id"],
                conversation_id=c["conversation_id"],
                memory_type=c["memory_type"],
                content=c["content"],
                start_msg_index=c["start_msg_index"],
                end_msg_index=c["end_msg_index"],
                source_message_ids=c["source_message_ids"],
                provider=c.get("provider", "Unknown"),
                confidence=float(c.get("confidence", 1.0)),
                status=c.get("status", "active"),
                created_at=c.get("created_at", ""),
                updated_at=c.get("updated_at", ""),
            )
            for c in candidates_raw
        ]

        # 2. Extract query keywords
        query_tokens = [t.lower() for t in re.findall(r"\w+", query_str) if len(t) > 1]

        # 3. Compute neural embeddings if model is available
        query_embedding = None
        if _EMBEDDING_MODEL is not None:
            try:
                query_embedding = _EMBEDDING_MODEL.encode(query_str, convert_to_tensor=True)
            except Exception as e:
                logger.warning(f"Embedding encoding failed for query '{query_str}': {e}")
                query_embedding = None

        scored_results: List[StructuredMemorySearchResult] = []

        for mem in candidate_memories:
            content_lower = mem.content.lower()
            mem_tokens = [t.lower() for t in re.findall(r"\w+", mem.content) if len(t) > 1]

            # Keyword lexical match
            matched_terms = [t for t in query_tokens if t in content_lower]
            keyword_score = len(matched_terms) / float(max(len(query_tokens), 1))

            # Semantic neural match
            semantic_score = 0.0
            if _EMBEDDING_MODEL is not None and query_embedding is not None:
                try:
                    mem_emb = _EMBEDDING_MODEL.encode(mem.content, convert_to_tensor=True)
                    cos_sim = float(util.cos_sim(query_embedding, mem_emb)[0][0])
                    semantic_score = max(0.0, min(1.0, cos_sim))
                except Exception:
                    semantic_score = 0.0
            else:
                # Lexical Jaccard fallback
                union_len = len(set(query_tokens).union(set(mem_tokens)))
                semantic_score = (len(matched_terms) / float(union_len)) if union_len > 0 else 0.0

            # Exact phrase bonus
            if query_str.lower() in content_lower:
                keyword_score = max(keyword_score, 0.9)

            # Hybrid Score calculation (0.6 semantic + 0.4 keyword)
            if query_embedding is not None:
                final_score = (0.6 * semantic_score) + (0.4 * keyword_score)
                match_type = "hybrid"
            else:
                final_score = max(keyword_score, semantic_score)
                match_type = "keyword"

            if final_score >= threshold:
                source_messages: List[Message] = []
                if hydrate_provenance:
                    source_messages = self.memory_repo.resolve_provenance_messages(mem)

                scored_results.append(
                    StructuredMemorySearchResult(
                        memory=mem,
                        score=final_score,
                        match_type=match_type,
                        matched_terms=matched_terms,
                        source_messages=source_messages,
                    )
                )

        # Sort by score descending
        scored_results.sort(key=lambda r: r.score, reverse=True)

        return scored_results[:limit]
