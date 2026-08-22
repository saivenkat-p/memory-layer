"""
Context Expander module (Milestone V6.4-C: Contextual Result Expansion).

Enriches ranked SearchResults with surrounding conversational context turns.
Guarantees:
1. Pure post-ranking enrichment — does NOT alter search scores or ranking order.
2. Configurable / testable expansion strategies:
   - 'adaptive': Content-aware & role-aware expansion (e.g. captures Q&A pairs for short utterances like 'Seee').
   - 'turn_aware': Ensures complete User + Assistant turn pairings.
   - 'fixed': Symmetric index-based windowing (before/after).
3. Preserves all message metadata (id, conversation_id, msg_index, role, content, timestamp).
4. Strictly preserves conversation isolation (no cross-conversation bleed).
5. Output order is always msg_index ASC with zero duplicate messages.
"""

import logging
from typing import List, Dict, Any, Optional
from app.models.schemas import Conversation, Message
from app.repositories.conversation_repository import ConversationRepository
from app.search.search_engine import SearchResult

logger = logging.getLogger(__name__)


class ContextExpander:
    """
    Service for expanding search results into rich, readable conversational context blocks.
    """

    def __init__(self, repo: Optional[ConversationRepository] = None):
        self.repo = repo or ConversationRepository()

    def expand_results(
        self,
        results: List[SearchResult],
        strategy: str = "adaptive",
        window_size: int = 1,
    ) -> List[SearchResult]:
        """
        Enriches a list of SearchResults with surrounding conversation context.

        Args:
            results: List of ranked SearchResult objects.
            strategy: Expansion strategy ('adaptive', 'turn_aware', 'fixed').
            window_size: Base window parameter for strategies.

        Returns:
            The same list of SearchResult objects with context_messages and context_text populated.
        """
        if not results:
            return []

        # Local cache for conversations within this batch to minimize DB lookups
        conv_cache: Dict[str, Optional[Conversation]] = {}

        for res in results:
            cid = res.conversation_id
            if cid not in conv_cache:
                try:
                    conv_cache[cid] = self.repo.get_conversation(cid)
                except Exception as e:
                    logger.error(f"Failed to fetch conversation {cid} for context expansion: {e}")
                    conv_cache[cid] = None

            conv = conv_cache.get(cid)
            self.expand_single_result(res, conv=conv, strategy=strategy, window_size=window_size)

        return results

    def expand_single_result(
        self,
        result: SearchResult,
        conv: Optional[Conversation] = None,
        strategy: str = "adaptive",
        window_size: int = 1,
    ) -> SearchResult:
        """
        Enriches a single SearchResult in-place.
        """
        if conv is None and result.conversation_id:
            try:
                conv = self.repo.get_conversation(result.conversation_id)
            except Exception as e:
                logger.error(f"Failed to fetch conversation {result.conversation_id}: {e}")
                conv = None

        if not conv or not conv.messages:
            # Fallback: self-contained single message context
            result.context_messages = [
                {
                    "id": result.message_id,
                    "conversation_id": result.conversation_id,
                    "role": result.matched_role,
                    "content": result.matched_content,
                    "msg_index": result.msg_index,
                    "timestamp": result.imported_at,
                }
            ]
            role_label = result.matched_role.capitalize() if result.matched_role else "Message"
            result.context_text = f"{role_label}: {result.matched_content.strip()}"
            return result

        all_msgs = conv.messages
        target_pos = -1

        # Locate target message by msg_index or message_id
        for pos, msg in enumerate(all_msgs):
            if msg.index == result.msg_index or msg.id == result.message_id:
                target_pos = pos
                break

        if target_pos == -1:
            # If target index not directly found, fallback to matched content
            result.context_messages = [
                {
                    "id": result.message_id,
                    "conversation_id": result.conversation_id,
                    "role": result.matched_role,
                    "content": result.matched_content,
                    "msg_index": result.msg_index,
                    "timestamp": result.imported_at,
                }
            ]
            role_label = result.matched_role.capitalize() if result.matched_role else "Message"
            result.context_text = f"{role_label}: {result.matched_content.strip()}"
            return result

        total_msgs = len(all_msgs)
        target_msg = all_msgs[target_pos]
        role_clean = str(target_msg.role).lower().strip()
        content_clean = str(target_msg.content).strip()
        is_short = len(content_clean) < 80 or len(content_clean.split()) <= 12

        # ---------------------------------------------------------------------
        # Determine Window Bounds [start_pos, end_pos)
        # ---------------------------------------------------------------------
        if strategy == "fixed":
            start_pos = max(0, target_pos - window_size)
            end_pos = min(total_msgs, target_pos + window_size + 1)

        elif strategy == "turn_aware":
            # Expand to ensure the complete turn pair is present
            if role_clean == "user":
                start_pos = max(0, target_pos - (window_size - 1))
                end_pos = min(total_msgs, target_pos + 1 + window_size)
            else:  # assistant / system
                start_pos = max(0, target_pos - window_size)
                end_pos = min(total_msgs, target_pos + window_size)

        else:
            # Default: 'adaptive' (content-length and role-aware)
            if is_short:
                # Short message (e.g. "Seee", "yes", "how?", "do that"):
                # Need both preceding context AND subsequent response
                if role_clean == "user":
                    start_pos = max(0, target_pos - 1)
                    end_pos = min(total_msgs, target_pos + 2)
                else:  # assistant
                    start_pos = max(0, target_pos - 2)
                    end_pos = min(total_msgs, target_pos + 1)
            else:
                # Normal/long message: standard turn expansion
                if role_clean == "user":
                    start_pos = max(0, target_pos)
                    end_pos = min(total_msgs, target_pos + 2)
                else:
                    start_pos = max(0, target_pos - 1)
                    end_pos = min(total_msgs, target_pos + 1)

        # Boundary clamping sanity check
        start_pos = max(0, min(start_pos, total_msgs - 1))
        end_pos = max(start_pos + 1, min(end_pos, total_msgs))

        # Extract ordered messages in slice
        slice_msgs = all_msgs[start_pos:end_pos]

        # ---------------------------------------------------------------------
        # Build context_messages & context_text
        # ---------------------------------------------------------------------
        context_messages: List[Dict[str, Any]] = []
        text_lines: List[str] = []

        for m in slice_msgs:
            context_messages.append(
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id or result.conversation_id,
                    "role": m.role,
                    "content": m.content,
                    "msg_index": m.index,
                    "timestamp": m.timestamp,
                }
            )
            role_label = m.role.capitalize() if m.role else "Message"
            text_lines.append(f"{role_label}: {m.content.strip()}")

        result.context_messages = context_messages
        result.context_text = "\n\n".join(text_lines)

        return result
