"""
Keyword Search Engine and Source Context Retrieval module.

Feature 4 (Keyword Search) & Feature 5 (Source Context):
Enables full-text keyword search across all stored conversation messages,
returns snippet matches with highlighted terms, and retrieves surrounding
message context (previous & following messages).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.models.schemas import Conversation, Message

STOPWORDS = {
    "what", "where", "which", "who", "whom", "whose", "why", "how", "can", "you",
    "find", "show", "tell", "have", "talked", "discussed", "about", "did", "the",
    "for", "and", "that", "this", "with", "from", "your", "some", "idea", "ideas"
}


@dataclass
class SearchResult:
    """
    Represents a matching message result from a search query.
    """
    message_id: str
    conversation_id: str
    conversation_title: str
    source: str
    imported_at: str
    matched_role: str
    matched_content: str
    snippet: str
    msg_index: int
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    score: int = 1
    context_messages: List[Dict[str, Any]] = field(default_factory=list)
    context_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "conversation_title": self.conversation_title,
            "source": self.source,
            "imported_at": self.imported_at,
            "matched_role": self.matched_role,
            "matched_content": self.matched_content,
            "snippet": self.snippet,
            "msg_index": self.msg_index,
            "category": self.category,
            "tags": self.tags,
            "score": self.score,
            "context_messages": self.context_messages,
            "context_text": self.context_text,
        }


class SearchEngine:
    """
    Executes SQL full-text/keyword queries and retrieves source context windows.
    """

    def __init__(self, repo: Optional[ConversationRepository] = None):
        self.repo = repo or ConversationRepository()

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[SearchResult]:
        """
        Searches for messages matching the given query and optional filters.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        raw_words = re.findall(r'\w+', clean_query.lower())
        keywords = [w for w in raw_words if len(w) > 1 and w not in STOPWORDS]

        if not keywords:
            keywords = [w for w in raw_words if len(w) > 1]

        if not keywords:
            return []

        # Build SQL query with OR/AND clauses and term frequency scoring
        sql = """
            SELECT 
                m.id as msg_id,
                m.conversation_id,
                m.role as msg_role,
                m.content as msg_content,
                m.msg_index,
                m.timestamp as msg_timestamp,
                c.title as conv_title,
                c.source as conv_source,
                c.imported_at as conv_imported_at,
                c.category as conv_category,
                c.tags as conv_tags,
                c.description as conv_desc
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE 1=1
        """

        params: List[Any] = []
        term_conditions = []

        for kw in keywords:
            pattern = f"%{kw}%"
            term_conditions.append(
                "(m.content LIKE ? OR c.title LIKE ? OR c.description LIKE ? OR c.category LIKE ? OR c.tags LIKE ?)"
            )
            params.extend([pattern, pattern, pattern, pattern, pattern])

        if term_conditions:
            sql += " AND (" + " OR ".join(term_conditions) + ")"

        if category and category.strip():
            sql += " AND c.category = ?"
            params.append(category.strip())

        if source and source.strip():
            sql += " AND c.source = ?"
            params.append(source.strip())

        if tag and tag.strip():
            sql += " AND c.tags LIKE ?"
            params.append(f"%{tag.strip()}%")

        sql += " ORDER BY c.imported_at DESC LIMIT 200"

        with self.repo.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

        results: List[SearchResult] = []
        for row in rows:
            content = row["msg_content"]
            title = row["conv_title"]
            category_val = row["conv_category"] or ""
            desc = row["conv_desc"] or ""
            tags_val = row["conv_tags"] or ""

            # Calculate match relevance score using BM25 term-frequency saturation and length normalization
            content_lower = content.lower()
            metadata_text = f"{title} {category_val} {desc} {tags_val}".lower()
            is_derived_title = title.startswith("Continued:") or title.startswith("Composed:")

            doc_words = max(1, len(content.split()))
            k1 = 1.2
            b = 0.75
            avgdl = 60.0
            len_norm = (1.0 - b) + b * (doc_words / avgdl)

            score = 0.0
            for kw in keywords:
                content_count = content_lower.count(kw)
                if content_count > 0:
                    bm25_tf = (content_count * (k1 + 1.0)) / (content_count + k1 * len_norm)
                    score += bm25_tf
                # Metadata bonus: +0.5 max per keyword (suppressed for derived continuation titles to prevent crowding out parent chats)
                if kw in metadata_text and not is_derived_title:
                    score += 0.5

            if score > 0:
                snippet = self._generate_snippet(content, keywords)
                tags_list = [t.strip() for t in tags_val.split(",") if t.strip()] if tags_val else []

                results.append(
                    SearchResult(
                        message_id=row["msg_id"],
                        conversation_id=row["conversation_id"],
                        conversation_title=row["conv_title"],
                        source=row["conv_source"],
                        imported_at=row["conv_imported_at"],
                        matched_role=row["msg_role"],
                        matched_content=content,
                        snippet=snippet,
                        msg_index=row["msg_index"],
                        category=row["conv_category"],
                        tags=tags_list,
                        score=score,
                    )
                )

        # Sort results by score DESC, then recency
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def get_source_context(
        self, conversation_id: str, target_index: int, window: int = 2
    ) -> Dict[str, Any]:
        """
        Feature 5 — Source Context:
        Retrieves target message along with surrounding messages.
        """
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            return {"conversation": None, "target_message": None, "context_messages": []}

        all_msgs = conversation.messages
        target_msg = None
        target_pos = -1

        for pos, msg in enumerate(all_msgs):
            if msg.index == target_index:
                target_msg = msg
                target_pos = pos
                break

        if target_pos == -1:
            return {"conversation": conversation, "target_message": None, "context_messages": []}

        start_pos = max(0, target_pos - window)
        end_pos = min(len(all_msgs), target_pos + window + 1)

        previous_msgs = all_msgs[start_pos:target_pos]
        following_msgs = all_msgs[target_pos + 1 : end_pos]

        return {
            "conversation": conversation,
            "target_message": target_msg,
            "previous_messages": previous_msgs,
            "following_messages": following_msgs,
            "window_messages": all_msgs[start_pos:end_pos],
        }

    def _generate_snippet(self, text: str, terms: List[str], max_length: int = 200) -> str:
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

        start = max(0, match_start - 60)
        end = min(len(text), match_start + 120)

        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet
