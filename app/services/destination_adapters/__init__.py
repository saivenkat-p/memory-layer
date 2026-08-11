"""
Destination Adapters Package for Personal AI Memory Layer (Milestone V5B).
"""

from app.services.destination_adapters.base import DestinationAdapter, DestinationResult
from app.services.destination_adapters.local import LocalExportAdapter
from app.services.destination_adapters.chatgpt import ChatGPTAdapter
from app.services.destination_adapters.gemini import GeminiAdapter
from app.services.destination_adapters.stubs import ClaudeAdapter
from app.services.destination_adapters.registry import DestinationRegistry

__all__ = [
    "DestinationAdapter",
    "DestinationResult",
    "LocalExportAdapter",
    "ChatGPTAdapter",
    "GeminiAdapter",
    "ClaudeAdapter",
    "DestinationRegistry",
]
