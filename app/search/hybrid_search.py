"""
Hybrid Search Engine module.

Combines Keyword/Lexical Search and Local Neural Semantic Vector Search
using configurable weighted score fusion and relevance thresholding.
"""

from typing import List, Optional, Dict, Tuple
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchEngine, SearchResult, STOPWORDS
from app.search.semantic_search import SemanticSearchEngine
from app.utils.text_normalizer import strip_injected_context


class HybridSearchEngine:
    """
    Fuses Lexical Keyword Search and Local Neural Vector Search into a unified hybrid ranking pipeline.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        min_relevance_threshold: float = 0.35,
    ):
        """
        Args:
            repo: ConversationRepository instance.
            semantic_weight: Weight for neural vector similarity (default 0.7).
            keyword_weight: Weight for normalized keyword match (default 0.3).
            min_relevance_threshold: Threshold below which results are excluded (default 0.35).
        """
        self.repo = repo or ConversationRepository()
        self.keyword_engine = SearchEngine(self.repo)
        self.semantic_engine = SemanticSearchEngine(self.repo)
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.min_relevance_threshold = min_relevance_threshold

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[SearchResult]:
        """
        Executes Hybrid Search combining Lexical Matching and Neural Embedding Similarity.
        """
        if not query or not query.strip():
            return []

        clean_query = strip_injected_context(query).strip()
        if not clean_query:
            return []
        words = [w.lower() for w in clean_query.split() if len(w) > 1 and w.lower() not in STOPWORDS]
        if not words:
            words = [w.lower() for w in clean_query.split() if len(w) > 1]

        # 1. Lexical Keyword Search Candidate Pool
        keyword_results = self.keyword_engine.search(
            clean_query, category=category, source=source, tag=tag, limit=limit * 2
        )
        keyword_map: Dict[str, SearchResult] = {res.message_id: res for res in keyword_results}
        max_kw_score = max([res.score for res in keyword_results], default=1)

        # 2. Neural Vector Semantic Search Candidate Pool
        semantic_tuples = self.semantic_engine.search_semantic(clean_query, limit=limit * 2)
        semantic_map: Dict[str, float] = {msg_id: score for msg_id, score in semantic_tuples}

        # 3. Candidate Pool Union
        all_msg_ids = set(keyword_map.keys()).union(set(semantic_map.keys()))

        hybrid_results: List[SearchResult] = []

        for msg_id in all_msg_ids:
            res = keyword_map.get(msg_id)

            if not res:
                convs = self.repo.list_conversations(limit=200)
                found_msg = None
                found_conv = None
                for c in convs:
                    for m in c.messages:
                        if m.id == msg_id:
                            found_msg = m
                            found_conv = c
                            break
                    if found_msg:
                        break

                if not found_msg or not found_conv:
                    continue

                snippet = self.keyword_engine._generate_snippet(found_msg.content, words)
                res = SearchResult(
                    message_id=found_msg.id,
                    conversation_id=found_conv.id,
                    conversation_title=found_conv.title,
                    source=found_conv.source,
                    imported_at=found_conv.imported_at,
                    matched_role=found_msg.role,
                    matched_content=found_msg.content,
                    snippet=snippet,
                    msg_index=found_msg.index,
                    category=found_conv.category,
                    tags=found_conv.tags,
                    score=0,
                )

            # Apply Category / Source / Tag filters to semantic candidates as well
            if category and res.category != category:
                continue
            if source and res.source != source:
                continue
            if tag and tag not in res.tags:
                continue

            # Normalized Keyword Score [0.0, 1.0]
            kw_raw = res.score
            kw_norm = kw_raw / float(max_kw_score) if max_kw_score > 0 else 0.0

            # Neural Cosine Semantic Score [0.0, 1.0]
            sem_score = semantic_map.get(msg_id, 0.0)

            # Combined Hybrid Score Formula with Adaptive Candidate Fusion (V6.4-A)
            # Candidates with keyword evidence use hybrid score weighting.
            # Pure semantic candidates (kw_norm == 0) use raw cosine similarity
            # to prevent artificial score dampening from missing keywords.
            if kw_norm > 0:
                final_score = (self.semantic_weight * sem_score) + (self.keyword_weight * kw_norm)
                threshold = self.min_relevance_threshold
            else:
                final_score = sem_score
                threshold = 0.38  # Adaptive semantic-only threshold

            # Apply Relevance Thresholding
            if final_score >= threshold:
                res.score = int(round(final_score * 100))
                hybrid_results.append(res)

        # Sort by Final Hybrid Score DESC
        hybrid_results.sort(key=lambda r: r.score, reverse=True)
        return hybrid_results[:limit]
