"""
Find Here Engine module (Version 3 Feature 1).

Executes ephemeral, in-conversation hybrid search strictly scoped to a single conversation.
Guarantee: Search queries are never persisted to SQLite, never inserted into messages,
and generate no persistent database embeddings.
"""

import re
import logging
from typing import List, Optional, Dict, Any

from app.models.schemas import Conversation, Message
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchResult, STOPWORDS
from app.search.semantic_search import SemanticSearchEngine
from app.search.context_expander import ContextExpander

logger = logging.getLogger(__name__)


class FindHereEngine:
    """
    Handles temporary, strictly scoped in-conversation search.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        min_relevance_threshold: float = 0.20,
    ):
        self.repo = repo or ConversationRepository()
        self.semantic_engine = SemanticSearchEngine(self.repo)
        self.expander = ContextExpander(self.repo)
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.min_relevance_threshold = min_relevance_threshold

    def search_in_conversation(
        self,
        conversation_id: str,
        query: str,
        limit: int = 20,
        expand_context: bool = True,
        expansion_strategy: str = "adaptive",
    ) -> List[SearchResult]:
        """
        Searches ONLY the currently selected conversation.

        Guarantees:
        - Query is NOT inserted into messages or conversations tables.
        - Query is NOT persisted.
        - Query creates NO persistent embedding.
        - Execution does NOT modify the database.

        Args:
            conversation_id: ID of the conversation to search within.
            query: User's search query string.
            limit: Maximum matches to return (default 20).

        Returns:
            List of SearchResult objects belonging exclusively to conversation_id.
        """
        if not query or not query.strip() or not conversation_id:
            return []

        conv = self.repo.get_conversation(conversation_id)
        if not conv or not conv.messages:
            return []

        clean_query = query.strip()
        raw_words = re.findall(r"\w+", clean_query.lower())
        keywords = [w for w in raw_words if len(w) > 1 and w not in STOPWORDS]
        if not keywords:
            keywords = [w for w in raw_words if len(w) > 1]

        # 1. Ephemeral Query Vector (in-memory only, not saved to DB)
        try:
            query_vec = self.semantic_engine.generate_embedding(clean_query)
        except Exception as e:
            logger.error(f"Failed to generate temporary query embedding: {e}")
            query_vec = []

        # 2. Fetch stored embeddings ONLY for messages in target conversation
        stored_embeddings: Dict[str, List[float]] = {}
        if query_vec:
            with self.repo.db.get_connection() as conn:
                cursor = conn.cursor()
                msg_ids = [m.id for m in conv.messages]
                placeholders = ",".join(["?"] * len(msg_ids))
                sql = f"SELECT message_id, embedding_json, model_name FROM message_embeddings WHERE message_id IN ({placeholders})"
                cursor.execute(sql, tuple(msg_ids))
                rows = cursor.fetchall()
                for r in rows:
                    is_valid, _, np_vec = self.semantic_engine.validate_stored_embedding(
                        r["embedding_json"], r["model_name"]
                    )
                    if is_valid and np_vec is not None:
                        stored_embeddings[r["message_id"]] = np_vec.tolist()

        # 3. Calculate Hybrid Scores per message in target conversation
        results: List[SearchResult] = []

        # Find max keyword score for normalization
        max_kw_score = 1
        kw_scores: Dict[str, int] = {}

        for msg in conv.messages:
            text_to_search = f"{msg.content} {conv.title}".lower()
            score = 0
            for kw in keywords:
                if kw in text_to_search:
                    score += text_to_search.count(kw)
            kw_scores[msg.id] = score
            if score > max_kw_score:
                max_kw_score = score

        for msg in conv.messages:
            kw_raw = kw_scores.get(msg.id, 0)
            kw_norm = kw_raw / float(max_kw_score) if max_kw_score > 0 else 0.0

            sem_score = 0.0
            if msg.id in stored_embeddings and query_vec:
                try:
                    import numpy as np
                    q_np = np.asarray(query_vec, dtype=np.float32)
                    m_np = np.asarray(stored_embeddings[msg.id], dtype=np.float32)
                    if len(q_np) == len(m_np) and len(q_np) > 0:
                        sim = float(np.dot(q_np, m_np))
                        sem_score = max(-1.0, min(1.0, sim))
                except Exception:
                    sem_score = 0.0

            final_score = (self.semantic_weight * sem_score) + (self.keyword_weight * kw_norm)

            if final_score >= self.min_relevance_threshold or kw_raw > 0:
                # Helper snippet generation
                snippet = self._generate_snippet(msg.content, keywords)
                results.append(
                    SearchResult(
                        message_id=msg.id,
                        conversation_id=conv.id,
                        conversation_title=conv.title,
                        source=conv.source,
                        imported_at=conv.imported_at,
                        matched_role=msg.role,
                        matched_content=msg.content,
                        snippet=snippet,
                        msg_index=msg.index,
                        category=conv.category,
                        tags=conv.tags,
                        score=int(round(final_score * 100)),
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        top_results = results[:limit]

        # V6.4-C: Contextual Result Expansion (Post-Ranking Stage)
        if expand_context and top_results:
            top_results = self.expander.expand_results(top_results, strategy=expansion_strategy)

        return top_results


    def _generate_snippet(self, text: str, terms: List[str], max_length: int = 180) -> str:
        if not text:
            return ""

        lower_text = text.lower()
        match_start = -1

        for term in terms:
            pos = lower_text.find(term.lower())
            if pos != -1:
                match_start = pos
                break

        if match_start == -1:
            return text[:max_length] + ("..." if len(text) > max_length else "")

        start = max(0, match_start - 40)
        end = min(len(text), match_start + 100)

        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet
