"""
Context Composer Service Module (Version 4: 🧩 Compose Context).

Enables provider-independent multi-topic & multi-conversation context composition:
1. Multi-topic hybrid search across complete indexed memory.
2. Grouping candidates by source conversation and AI provider.
3. Candidate selection, deselection, and user reordering.
4. Preview generation and provider-independent payload export.
5. Creation of derived Composed Conversations with source provenance and multi-parent DB relationships.
"""

import re
import uuid
import logging
from typing import List, Optional, Dict, Any, Tuple

from app.models.schemas import Conversation, Message, ContextCandidate, ComposedContext
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.search.search_engine import SearchResult

logger = logging.getLogger(__name__)


class ContextComposer:
    """
    Core engine for multi-topic / multi-conversation context composition.
    """

    def __init__(
        self,
        repo: Optional[ConversationRepository] = None,
        search_engine: Optional[HybridSearchEngine] = None,
    ):
        self.repo = repo or ConversationRepository()
        self.search_engine = search_engine or HybridSearchEngine(self.repo)

    def decompose_query(self, query: str) -> List[str]:
        """
        Decomposes a complex multi-topic query string into distinct topic sub-queries.
        Example:
        'Bring together everything about my Memory Layer, funding strategy, and using it across ChatGPT/Gemini.'
        -> ['Memory Layer', 'funding strategy', 'using it across ChatGPT Gemini']
        """
        if not query or not query.strip():
            return []

        text = query.strip()
        
        # Remove common filler lead-in phrases
        lead_ins = [
            r"^(bring|gather|collect|find|get)\s+(together\s+)?(everything\s+)?(all\s+)?(about\s+)?",
            r"^(show|give)\s+me\s+(everything\s+)?(all\s+)?(about\s+)?",
            r"^(i\s+want\s+to\s+)?(combine|compose)\s+",
        ]
        for pattern in lead_ins:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        # Split on commas, ' and ', ' + ', ' as well as ', ' with '
        delimiters = r",|\s+and\s+|\s*\+\s*|\s+as\s+well\s+as\s+"
        parts = [p.strip() for p in re.split(delimiters, text, flags=re.IGNORECASE) if p.strip()]

        final_topics = []
        for p in parts:
            clean_p = re.sub(r"[^\w\s-]", " ", p).strip()
            if len(clean_p) > 2 and clean_p.lower() not in {"everything", "about", "using", "across", "chats"}:
                final_topics.append(clean_p)

        if not final_topics:
            final_topics = [query.strip()]

        # Include full query if multi-topic decomposition produced sub-parts
        if len(final_topics) == 1 and query.strip() != final_topics[0]:
            final_topics.append(query.strip())

        return list(dict.fromkeys(final_topics))

    def search_context(
        self, query: str, limit: int = 50
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes multi-topic search across complete indexed memory history using query decomposition,
        candidate deduplication, parent vs continuation reranking, and diagnostics tracking.

        Args:
            query: User composition query string (e.g. 'Memory Layer, funding strategy, cross-AI integration').
            limit: Maximum candidate pool size per topic.

        Returns:
            Dictionary mapping conversation_id -> {
                "conversation_id": str,
                "title": str,
                "source": str,
                "max_score": int,
                "is_derived": bool,
                "candidates": List[ContextCandidate]
            }
            plus a special '_diagnostics' dictionary.
        """
        if not query or not query.strip():
            return {}

        clean_query = query.strip()
        topics = self.decompose_query(clean_query)
        
        raw_candidates_map: Dict[str, ContextCandidate] = {}
        topic_counts: Dict[str, int] = {}
        total_raw_candidates = 0

        # Execute search per sub-topic
        for topic in topics:
            results: List[SearchResult] = self.search_engine.search(topic, limit=25)
            topic_counts[topic] = len(results)
            total_raw_candidates += len(results)

            for res in results:
                msg_id = res.message_id
                cid = res.conversation_id
                title = res.conversation_title
                is_derived = title.startswith("Continued:") or title.startswith("Composed:")

                # Calculate raw semantic score
                raw_sem = 0.0
                try:
                    query_vec = self.search_engine.semantic_engine.generate_embedding(topic)
                    stored_rows = self.repo.db.get_connection().cursor().execute(
                        "SELECT embedding_json, model_name FROM message_embeddings WHERE message_id = ?", (msg_id,)
                    ).fetchone()
                    if stored_rows:
                        valid, _, np_vec = self.search_engine.semantic_engine.validate_stored_embedding(
                            stored_rows["embedding_json"], stored_rows["model_name"]
                        )
                        if valid and np_vec is not None:
                            import numpy as np
                            q_np = np.asarray(query_vec, dtype=np.float32)
                            if len(q_np) == len(np_vec) and len(q_np) > 0:
                                raw_sem = max(-1.0, min(1.0, float(np.dot(q_np, np_vec))))
                except Exception:
                    raw_sem = 0.0

                cand = ContextCandidate(
                    message_id=msg_id,
                    conversation_id=cid,
                    conversation_title=title,
                    source=res.source,
                    role=res.matched_role,
                    content=res.matched_content,
                    message_index=res.msg_index,
                    relevance_score=res.score,
                    timestamp=res.imported_at,
                    topic_association=topic,
                    raw_semantic_score=round(raw_sem, 4),
                    keyword_score=res.score,
                    is_derived=is_derived,
                )

                # Deduplicate: if candidate message already seen, keep candidate with higher relevance score
                if msg_id in raw_candidates_map:
                    if cand.relevance_score > raw_candidates_map[msg_id].relevance_score:
                        raw_candidates_map[msg_id] = cand
                else:
                    raw_candidates_map[msg_id] = cand

        duplicates_removed = total_raw_candidates - len(raw_candidates_map)

        final_candidates = list(raw_candidates_map.values())
        
        # Group candidates by conversation_id
        grouped: Dict[str, Dict[str, Any]] = {}
        for cand in final_candidates:
            cid = cand.conversation_id
            if cid not in grouped:
                grouped[cid] = {
                    "conversation_id": cid,
                    "title": cand.conversation_title,
                    "source": cand.source,
                    "max_score": cand.relevance_score,
                    "is_derived": cand.is_derived,
                    "candidates": [],
                }
            
            grouped[cid]["candidates"].append(cand)
            if cand.relevance_score > grouped[cid]["max_score"]:
                grouped[cid]["max_score"] = cand.relevance_score

        # Sort candidates inside each conversation by message_index
        for cid in grouped:
            grouped[cid]["candidates"].sort(key=lambda c: c.message_index)

        # Sort conversation groups: Original parent conversations first (is_derived=False), then by max_score DESC
        sorted_conv_ids = sorted(
            grouped.keys(),
            key=lambda k: (1 if grouped[k]["is_derived"] else 0, -grouped[k]["max_score"])
        )

        sorted_grouped: Dict[str, Dict[str, Any]] = {cid: grouped[cid] for cid in sorted_conv_ids}

        # Attach Diagnostics metadata
        providers = set(g["source"] for g in sorted_grouped.values())
        sorted_grouped["_diagnostics"] = {
            "query": query,
            "detected_topics": topics,
            "candidates_per_topic": topic_counts,
            "total_raw_candidates": total_raw_candidates,
            "duplicates_removed": duplicates_removed,
            "conversations_found": len(sorted_grouped),
            "providers_found": len(providers),
            "reranking_applied": True,
        }

        return sorted_grouped

    def build_context_preview(
        self, selected_candidates: List[ContextCandidate], query: str = "", title: str = ""
    ) -> ComposedContext:
        """
        Constructs a ComposedContext preview object from selected candidate list.
        """
        comp_id = str(uuid.uuid4())
        comp_title = title.strip() if title and title.strip() else f"Composed: {query.strip()[:30]}"
        
        # Deduplicate while preserving order
        unique_candidates: List[ContextCandidate] = []
        seen_ids = set()
        for cand in selected_candidates:
            if cand.message_id not in seen_ids:
                seen_ids.add(cand.message_id)
                unique_candidates.append(cand)

        return ComposedContext(
            composition_id=comp_id,
            title=comp_title,
            query=query.strip(),
            selected_candidates=unique_candidates,
        )

    def reorder_context(
        self, candidates: List[ContextCandidate], ordered_ids: List[str]
    ) -> List[ContextCandidate]:
        """
        Reorders a list of candidate messages according to ordered_ids list.
        """
        cand_map = {c.message_id: c for c in candidates}
        reordered: List[ContextCandidate] = []
        seen = set()

        for mid in ordered_ids:
            if mid in cand_map and mid not in seen:
                reordered.append(cand_map[mid])
                seen.add(mid)

        # Append any candidates missing from ordered_ids to prevent loss
        for c in candidates:
            if c.message_id not in seen:
                reordered.append(c)
                seen.add(c.message_id)

        return reordered

    def create_composed_conversation(
        self,
        title: str,
        query: str,
        selected_candidates: List[ContextCandidate],
    ) -> Tuple[Conversation, ComposedContext]:
        """
        Creates and persists a derived Composed Conversation in SQLite DB.

        Guarantees:
        - Source conversations/messages remain 100% immutable.
        - Message provenance (source_conversation_id, source_message_id) is preserved.
        - Multiple parent-child relationships are stored in conversation_relationships.
        - Provider-independent export structure is generated.

        Returns:
            Tuple of (new_child_conversation, composed_context_instance)
        """
        if not selected_candidates:
            raise ValueError("Cannot create composed conversation without selected context messages.")

        composed_ctx = self.build_context_preview(selected_candidates, query=query, title=title)

        child_messages: List[Message] = []
        unique_sources: Dict[str, str] = {}

        for idx, cand in enumerate(composed_ctx.selected_candidates):
            child_messages.append(
                Message(
                    role=cand.role,
                    content=cand.content,
                    index=idx,
                    timestamp=cand.timestamp,
                    source_conversation_id=cand.conversation_id,
                    source_message_id=cand.message_id,
                )
            )
            unique_sources[cand.conversation_id] = cand.conversation_title

        child_title = composed_ctx.title
        if not child_title.lower().startswith("composed:"):
            child_title = f"Composed: {child_title}"

        # Combine source tags
        composed_conv = Conversation(
            title=child_title,
            messages=child_messages,
            source="Context Composition",
            category="Context Composition",
            tags=["Composed", "Multi-Topic"],
            description=f"Composed context derived from {len(unique_sources)} conversation(s) across {len(composed_ctx.source_providers)} provider(s). Query: '{query}'.",
        )

        # Save child conversation to SQLite repository
        self.repo.save_conversation(composed_conv)

        # Record parent-child relationship for EACH unique source conversation
        for parent_id, parent_title in unique_sources.items():
            self.repo.add_relationship(
                parent_id=parent_id,
                child_id=composed_conv.id,
                topic=query,
                rel_type="context_composition",
            )

        return composed_conv, composed_ctx
