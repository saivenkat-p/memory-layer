"""
Destination Registry module (Milestone V5B: Live AI Integration).

Factory registry that instantiates and manages available V5 destination adapters:
- Local Export Adapter
- ChatGPT (OpenAI API) Adapter
- Gemini Adapter (Stub)
- Claude Adapter (Stub)
"""

import logging
from typing import Dict, List, Optional, Type, Any

from app.services.destination_adapters.base import DestinationAdapter
from app.services.destination_adapters.local import LocalExportAdapter
from app.services.destination_adapters.chatgpt import ChatGPTAdapter
from app.services.destination_adapters.stubs import GeminiAdapter, ClaudeAdapter

logger = logging.getLogger(__name__)


class DestinationRegistry:
    """
    Registry factory for destination adapters.
    """

    def __init__(self, mock_chatgpt_executor: Optional[Any] = None):
        self.adapters: Dict[str, DestinationAdapter] = {
            "Local Export (JSON & Plain Text)": LocalExportAdapter(),
            "ChatGPT (OpenAI API)": ChatGPTAdapter(mock_executor=mock_chatgpt_executor),
            "Gemini (Google AI API)": GeminiAdapter(),
            "Claude (Anthropic API)": ClaudeAdapter(),
        }

    def get_adapter(self, provider_name: str) -> Optional[DestinationAdapter]:
        """
        Retrieves matching adapter instance by provider name or key snippet.
        """
        if not provider_name:
            return None

        # Direct match
        if provider_name in self.adapters:
            return self.adapters[provider_name]

        # Key snippet match
        clean_name = provider_name.lower()
        if "chatgpt" in clean_name or "openai" in clean_name:
            return self.adapters["ChatGPT (OpenAI API)"]
        elif "gemini" in clean_name or "google" in clean_name:
            return self.adapters["Gemini (Google AI API)"]
        elif "claude" in clean_name or "anthropic" in clean_name:
            return self.adapters["Claude (Anthropic API)"]
        elif "local" in clean_name:
            return self.adapters["Local Export (JSON & Plain Text)"]

        return None

    def list_adapters(self) -> List[DestinationAdapter]:
        """Returns list of all registered adapter instances."""
        return list(self.adapters.values())

    def list_provider_names(self) -> List[str]:
        """Returns list of all registered provider names."""
        return list(self.adapters.keys())
