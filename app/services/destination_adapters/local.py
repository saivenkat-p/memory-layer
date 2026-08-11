"""
Local Export Destination Adapter (Milestone V5B).

Wraps LocalExportDestination service to operate 100% offline within the V5B DestinationAdapter contract.
"""

from typing import Dict, Any, Optional
from app.models.schemas import PortableContextPackage
from app.services.destination_adapters.base import DestinationAdapter, DestinationResult
from app.services.export_engine import LocalExportDestination


class LocalExportAdapter(DestinationAdapter):
    """
    Concrete Local Export Destination Adapter.
    Enables offline JSON & Plain-Text package generation.
    """

    def __init__(self, exporter: Optional[LocalExportDestination] = None):
        self.exporter = exporter or LocalExportDestination()

    @property
    def provider_name(self) -> str:
        return "Local Export (JSON & Plain Text)"

    @property
    def is_supported(self) -> bool:
        return True

    def validate(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        if not package:
            return DestinationResult(
                status="VALIDATION_ERROR",
                provider=self.provider_name,
                message="PortableContextPackage cannot be None.",
                error_code="NULL_PACKAGE"
            )

        if package.schema_version != "1.0":
            return DestinationResult(
                status="VALIDATION_ERROR",
                provider=self.provider_name,
                message=f"Unsupported schema version '{package.schema_version}'. Expected '1.0'.",
                error_code="UNSUPPORTED_SCHEMA_VERSION"
            )

        if not package.messages:
            return DestinationResult(
                status="VALIDATION_ERROR",
                provider=self.provider_name,
                message="PortableContextPackage contains no selected messages.",
                error_code="EMPTY_MESSAGES"
            )

        return DestinationResult(
            status="SUCCESS",
            provider=self.provider_name,
            message="Package is valid for local export."
        )

    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        val_res = self.validate(package)
        if val_res.status != "SUCCESS":
            raise ValueError(val_res.message)

        return {
            "json_payload": self.exporter.export_json(package),
            "text_payload": self.exporter.export_text(package),
            "schema_version": package.schema_version,
            "package_id": package.package_id,
            "total_messages": len(package.messages),
        }

    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        val_res = self.validate(package, config)
        if val_res.status != "SUCCESS":
            return val_res

        try:
            payload = self.prepare(package)
            return DestinationResult(
                status="SUCCESS",
                provider=self.provider_name,
                message=f"Local export prepared successfully ({len(package.messages)} messages, schema v{package.schema_version}).",
                external_id=package.package_id,
                response_payload=payload
            )
        except Exception as e:
            return DestinationResult(
                status="VALIDATION_ERROR",
                provider=self.provider_name,
                message=f"Local export preparation failed: {e}",
                error_code="PREPARATION_FAILED"
            )
