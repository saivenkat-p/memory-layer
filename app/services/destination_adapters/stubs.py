"""
Destination Adapter Stubs for Claude (Milestone V5B).

Explicit NOT_SUPPORTED stub for Claude API adapter.
"""

from typing import Dict, Any, Optional
from app.models.schemas import PortableContextPackage
from app.services.destination_adapters.base import DestinationAdapter, DestinationResult


class ClaudeAdapter(DestinationAdapter):
    """
    Explicit stub for Anthropic Claude API Adapter (Planned for future release).
    """

    @property
    def provider_name(self) -> str:
        return "Claude (Anthropic API)"

    @property
    def is_supported(self) -> bool:
        return False

    def validate(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        return DestinationResult(
            status="NOT_SUPPORTED",
            provider=self.provider_name,
            message="Anthropic Claude API integration adapter is planned for a future release.",
            error_code="NOT_IMPLEMENTED"
        )

    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        raise NotImplementedError("ClaudeAdapter is not supported in the current release.")

    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        return self.validate(package, config)
