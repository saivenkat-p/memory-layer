"""
Export Engine and AI Destination Adapters (Milestone V5A: Live AI Integration Foundation).

Establishes the clean contract between V4 Context Composition and V5 AI Destinations:
1. Provider-independent PortableContextPackage creation.
2. Deterministic context text generation.
3. Destination-independent abstraction interface (BaseDestinationAdapter).
4. Local export adapter (LocalExportDestination) for JSON & Plain-Text exports without network calls.
"""

import abc
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.models.schemas import ComposedContext, ContextCandidate, PortableContextPackage

logger = logging.getLogger(__name__)


class BaseDestinationAdapter(abc.ABC):
    """
    Abstract base class for all V5 destination adapters.
    """

    @abc.abstractmethod
    def prepare_context(self, composed_context: ComposedContext) -> PortableContextPackage:
        """Transforms a ComposedContext instance into a PortableContextPackage."""
        pass

    @abc.abstractmethod
    def generate_context_text(self, composed_context: ComposedContext) -> str:
        """Generates a deterministic plain-text / markdown context string."""
        pass

    @abc.abstractmethod
    def export_json(self, package: PortableContextPackage) -> str:
        """Serializes package to JSON."""
        pass

    @abc.abstractmethod
    def export_text(self, package: PortableContextPackage) -> str:
        """Exports package context text."""
        pass


class LocalExportDestination(BaseDestinationAdapter):
    """
    Concrete Local Export Destination Adapter (V5A Foundation).
    Enables local JSON and Plain-Text exports without external network or API calls.
    """

    def prepare_context(self, composed_context: ComposedContext) -> PortableContextPackage:
        """
        Creates a versioned, provider-independent PortableContextPackage (schema_version="1.0").
        """
        if not composed_context:
            raise ValueError("ComposedContext cannot be None.")

        package_id = str(uuid.uuid4())
        
        topic = composed_context.query.strip() if (composed_context.query and composed_context.query.strip()) else "Multi-Topic Context"
        
        if composed_context.title and composed_context.title.strip() and composed_context.title.strip() != "Composed:":
            title = composed_context.title.strip()
        else:
            title = f"Composed: {topic}"

        context_text = self.generate_context_text(composed_context)

        messages_payload: List[Dict[str, Any]] = []
        provenance_payload: List[Dict[str, Any]] = []

        for idx, cand in enumerate(composed_context.selected_candidates, start=1):
            msg_dict = {
                "order": idx,
                "message_id": cand.message_id,
                "conversation_id": cand.conversation_id,
                "conversation_title": cand.conversation_title,
                "provider": cand.source,
                "role": cand.role,
                "content": cand.content,
                "message_index": cand.message_index,
                "timestamp": cand.timestamp,
            }
            messages_payload.append(msg_dict)

            prov_dict = {
                "order": idx,
                "message_id": cand.message_id,
                "source_conversation_id": cand.conversation_id,
                "source_provider": cand.source,
                "original_index": cand.message_index,
            }
            provenance_payload.append(prov_dict)

        return PortableContextPackage(
            package_id=package_id,
            title=title,
            topic=topic,
            context_text=context_text,
            source_conversations=composed_context.source_conversations,
            source_providers=composed_context.source_providers,
            messages=messages_payload,
            provenance=provenance_payload,
            schema_version="1.0",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_context_text(self, composed_context: ComposedContext) -> str:
        """
        Generates a deterministic plain-text / markdown representation of the composed context.
        Groups selected messages by source conversation while preserving user-defined order.
        """
        if not composed_context or not composed_context.selected_candidates:
            return "# Context from Personal AI Memory Layer\n\n*No selected context messages available.*"

        topic_str = composed_context.query.strip() if (composed_context.query and composed_context.query.strip()) else composed_context.title.strip()

        lines = [
            "# Context from Personal AI Memory Layer",
            "",
            "## User's Goal / Topic",
            topic_str,
            "",
            "## Source Context Messages",
            "",
        ]

        # Group by conversation while maintaining first-seen order
        seen_convs = []
        conv_messages: Dict[str, List[ContextCandidate]] = {}

        for cand in composed_context.selected_candidates:
            cid = cand.conversation_id
            if cid not in conv_messages:
                seen_convs.append((cid, cand.conversation_title, cand.source))
                conv_messages[cid] = []
            conv_messages[cid].append(cand)

        for idx, (cid, title, provider) in enumerate(seen_convs, start=1):
            lines.append(f"### Source {idx}: {title}")
            lines.append(f"- Provider: {provider}")
            lines.append(f"- Conversation ID: {cid}")
            lines.append("")

            for msg in conv_messages[cid]:
                role_tag = f"[{msg.role.title()}]"
                lines.append(f"{role_tag}")
                lines.append(msg.content.strip())
                lines.append("")

        return "\n".join(lines).strip()

    def export_json(self, package: PortableContextPackage) -> str:
        """Exports JSON representation of package."""
        return package.to_json(indent=2)

    def export_text(self, package: PortableContextPackage) -> str:
        """Exports plain-text representation of package."""
        return package.context_text
