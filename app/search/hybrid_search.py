"""
Hybrid Search Engine module.

Fuses Lexical/Keyword Search and Semantic Embeddings Vector Search using
Score Fusion Ranking and Semantic Noise Filtering.
"""

from typing import List, Optional, Dict, Tuple
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchEngine, SearchResult, STOPWORDS
from app.search.semantic_search import SemanticSearchEngine


class HybridSearchEngine:
    """
    Combines Keyword Search and Semantic Vector Search into a unified, ranked Hybrid Search pipeline.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        alpha: float = 0.6,
    ):
        """
        Args:
            repo: ConversationRepository instance.
            alpha: Semantic weight factor (0.0 = pure keyword, 1.0 = pure semantic). Default 0.6.
        """
        self.repo = repo or ConversationRepository()
        self.keyword_engine = SearchEngine(self.repo)
        self.semantic_engine = SemanticSearchEngine(self.repo)
        self.alpha = alpha

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[SearchResult]:
        """
        Executes hybrid search combining lexical matching and vector semantic similarity.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        words = [w.lower() for w in clean_query.split() if len(w) > 1 and w.lower() not in STOPWORDS]
        if not words:
            words = [w.lower() for w in clean_query.split() if len(w) > 1]

        # 1. Execute Lexical Keyword Search
        keyword_results = self.keyword_engine.search(
            clean_query, category=category, source=source, tag=tag, limit=limit * 2
        )
        keyword_map: Dict[str, SearchResult] = {res.message_id: res for res in keyword_results}
        max_kw_score = max([res.score for res in keyword_results], default=1)

        # 2. Execute Semantic Vector Search
        semantic_tuples = self.semantic_engine.search_semantic(clean_query, limit=limit * 2)
        semantic_map: Dict[str, float] = {msg_id: score for msg_id, score in semantic_tuples}

        # 3. Candidate Pool Union
        all_msg_ids = set(keyword_map.keys()).union(set(semantic_map.keys()))

        hybrid_results: List[SearchResult] = []

        for msg_id in all_msg_ids:
            res = keyword_map.get(msg_id)

            # If not in keyword results, retrieve message from repo to construct SearchResult
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

            # Calculate Normalized Keyword Score [0, 1]
            kw_raw = res.score
            kw_norm = kw_raw / float(max_kw_score) if max_kw_score > 0 else 0.0

            # Calculate Semantic Cosine Score [0, 1]
            sem_score = semantic_map.get(msg_id, 0.0)

            # --- FALSE POSITIVE MITIGATION RULE ---
            # If user query has multiple words (e.g. "climbing mountain prototype") and only 1 keyword matches,
            # but semantic score is zero/near-zero because the core query concepts ("climbing mountain") do not match,
            # discard or heavily penalize the match.
            matched_kw_count = sum(1 for w in words if w in res.matched_content.lower() or w in res.conversation_title.lower())
            
            if len(words) >= 2 and matched_kw_count < len(words) and sem_score < 0.2:
                # Incidental match penalty
                kw_norm *= 0.1
                sem_score *= 0.1

            # Compute Hybrid Fused Score
            hybrid_score = (self.alpha * sem_score) + ((1.0 - self.alpha) * kw_norm)

            if hybrid_score > 0.05:
                # Update result score as percentage integer for clear UI display
                res.score = int(round(hybrid_score * 100))
                hybrid_results.append(res)

        # Sort by Hybrid Score DESC
        hybrid_results.sort(key=lambda r: r.score, reverse=True)
        return hybrid_results[:limit]
