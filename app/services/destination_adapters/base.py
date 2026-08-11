"""
Base Destination Adapter and DestinationResult contracts for Milestone V5B (Live AI Integration).

Defines:
1. DestinationResult normalized response schema.
2. DestinationAdapter abstract base class contract.
"""

import abc
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.models.schemas import PortableContextPackage

logger = logging.getLogger(__name__)


@dataclass
class DestinationResult:
    """
    Normalized response structure for all V5 destination adapters.
    Status values:
    - SUCCESS: Handoff / API execution completed successfully.
    - REDIRECT: Prepared URL or redirect link ready.
    - COPY_READY: Context formatted for clipboard.
    - API_RESPONSE: Response received from provider API.
    - AUTH_REQUIRED: Missing or invalid API credential.
    - NOT_SUPPORTED: Provider destination not supported in current build.
    - VALIDATION_ERROR: Invalid package schema or structure.
    - NETWORK_ERROR: External HTTP network request failed.
    - USER_CANCELLED: User explicitly cancelled transfer at privacy gate.
    """
    status: str
    provider: str
    message: str
    destination_url: Optional[str] = None
    copied_to_clipboard: bool = False
    external_id: Optional[str] = None
    error_code: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary without exposing sensitive fields."""
        return {
            "status": self.status,
            "provider": self.provider,
            "message": self.message,
            "destination_url": self.destination_url,
            "copied_to_clipboard": self.copied_to_clipboard,
            "external_id": self.external_id,
            "error_code": self.error_code,
            "has_payload": self.response_payload is not None,
        }


class DestinationAdapter(abc.ABC):
    """
    Abstract Base Class for provider destination adapters.
    All destination implementations (Local, ChatGPT, Gemini, Claude) inherit from this interface.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'Local Export', 'ChatGPT (OpenAI API)', 'Gemini (Google AI)')."""
        pass

    @property
    @abc.abstractmethod
    def is_supported(self) -> bool:
        """Returns True if the destination adapter is fully implemented and supported."""
        pass

    @abc.abstractmethod
    def validate(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        """Validates package schema_version, messages presence, and required credentials."""
        pass

    @abc.abstractmethod
    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        """Transforms PortableContextPackage into provider-specific payload structure."""
        pass

    @abc.abstractmethod
    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        """Executes context handoff or transmission to destination."""
        pass
