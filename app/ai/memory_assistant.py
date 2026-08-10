"""
Ask My Memory Assistant module using Hybrid Search.

Feature 6 (Ask My Memory):
Retrieves stored conversation content using Hybrid Search (Keyword + Semantic Vectors)
and synthesizes a grounded answer with clear distinction between SOURCE INFORMATION and AI SUMMARY.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from app.search.hybrid_search import HybridSearchEngine
from app.search.search_engine import SearchResult


@dataclass
class MemoryAnswer:
    """
    Represents the output answer from 'Ask My Memory'.
    """
    query: str
    found: bool
    summary: str
    sources: List[SearchResult] = field(default_factory=list)
    formatted_sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "found": self.found,
            "summary": self.summary,
            "sources": [s.to_dict() for s in self.sources],
            "formatted_sources": self.formatted_sources,
        }


class AskMyMemoryAssistant:
    """
    Executes grounded retrieval and builds attributed answers strictly based on stored memory.
    """

    def __init__(self, search_engine: Optional[HybridSearchEngine] = None):
        self.search_engine = search_engine or HybridSearchEngine()

    def ask(self, query: str, limit: int = 5) -> MemoryAnswer:
        """
        Processes a natural language query against stored memory using Hybrid Search.
        """
        if not query or not query.strip():
            return MemoryAnswer(
                query=query,
                found=False,
                summary="Please enter a question to ask your memory layer.",
                sources=[],
            )

        clean_query = query.strip()
        search_results = self.search_engine.search(clean_query, limit=limit)

        if not search_results:
            return MemoryAnswer(
                query=clean_query,
                found=False,
                summary=f"No relevant information found in your stored conversations for: '{clean_query}'.",
                sources=[],
            )

        formatted_sources = []
        summary_lines = []

        summary_lines.append(f"Based on **{len(search_results)} stored memory item(s)** matching your query:\n")

        for idx, res in enumerate(search_results, 1):
            source_ref = {
                "ref_num": idx,
                "conversation_title": res.conversation_title,
                "conversation_id": res.conversation_id,
                "source": res.source,
                "role": res.matched_role,
                "content_snippet": res.snippet,
                "message_index": res.msg_index,
                "category": res.category or "General",
                "tags": res.tags,
                "score": res.score,
            }
            formatted_sources.append(source_ref)

            role_label = "User" if res.matched_role.lower() == "user" else "Assistant"
            summary_lines.append(
                f"**[{idx}] {res.conversation_title}** ({res.source}) — Relevance Score: {res.score}%\n"
                f"> *{role_label}*: \"{res.snippet}\"\n"
            )

        summary_text = "\n".join(summary_lines)

        return MemoryAnswer(
            query=clean_query,
            found=True,
            summary=summary_text,
            sources=search_results,
            formatted_sources=formatted_sources,
        )
