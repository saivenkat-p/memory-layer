"""
Gemini (Google AI API) Destination Adapter (Milestone V5B: Live AI Integration).

Transforms a PortableContextPackage into native contents array for official Google Gemini API:
1. Clearly distinguishes historical reference context in system_instruction.
2. Preserves ordered multi-turn structure of package.messages (mapping assistant to 'model' role).
3. Transmits ONLY the user-selected package messages (never full SQLite DB).
4. Supports environment variable (GEMINI_API_KEY) or UI configuration without logging secrets.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

from app.models.schemas import PortableContextPackage
from app.services.destination_adapters.base import DestinationAdapter, DestinationResult

logger = logging.getLogger(__name__)

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


class GeminiAdapter(DestinationAdapter):
    """
    Concrete Destination Adapter for official Google Gemini API.
    """

    def __init__(self, mock_executor: Optional[Any] = None):
        """
        Args:
            mock_executor: Optional mock callable `(url, api_key, payload_bytes) -> (status_code, response_dict)`
                           used for unit testing to avoid real HTTP network calls.
        """
        self.mock_executor = mock_executor

    @property
    def provider_name(self) -> str:
        return "Gemini (Google AI API)"

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

        # Check API Key
        config_dict = config or {}
        api_key = config_dict.get("api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key or not str(api_key).strip():
            return DestinationResult(
                status="AUTH_REQUIRED",
                provider=self.provider_name,
                message="Missing GEMINI_API_KEY credential. Please set GEMINI_API_KEY environment variable or enter key in settings.",
                error_code="MISSING_API_KEY"
            )

        return DestinationResult(
            status="SUCCESS",
            provider=self.provider_name,
            message="Package and credentials validated for Google Gemini API transmission."
        )

    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        """
        Transforms PortableContextPackage v1.0 into native Gemini generateContent payload:
        - System instruction tags historical context.
        - Preserves ordered multi-turn structure (mapping 'assistant' role to 'model').
        """
        if not package or not package.messages:
            raise ValueError("Invalid package for Gemini preparation.")

        conv_titles = ", ".join(c.get("title", "") for c in package.source_conversations)

        system_instruction_text = (
            "You are an AI assistant. The user is providing historical reference context retrieved from their "
            "Personal AI Memory Layer across past conversations.\n"
            f"Topic / Goal: {package.topic}\n"
            f"Source Conversations ({len(package.source_conversations)}): {conv_titles}\n"
            "IMPORTANT: Treat the following user and model messages as historical reference material from past sessions, "
            "not as direct prior outputs in this current active session. Use this context to assist the user with their current objective."
        )

        contents: List[Dict[str, Any]] = []
        for msg in package.messages:
            role = "user" if msg.get("role") == "user" else "model"
            prov_info = f"[Historical Context - Provider: {msg.get('provider', 'Unknown')} | Conv: {msg.get('conversation_title', '')}]"
            msg_text = f"{prov_info}\n{msg.get('content', '')}"
            contents.append({
                "role": role,
                "parts": [{"text": msg_text}]
            })

        return {
            "system_instruction": {
                "parts": [{"text": system_instruction_text}]
            },
            "contents": contents,
        }

    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        """
        Executes transmission to Google Gemini API.
        """
        val_res = self.validate(package, config)
        if val_res.status != "SUCCESS":
            return val_res

        config_dict = config or {}
        api_key = config_dict.get("api_key") or os.environ.get("GEMINI_API_KEY")

        payload_dict = self.prepare(package)
        target_url = f"{GEMINI_API_ENDPOINT}?key={api_key.strip()}"

        # Mock Execution Path (Used during automated unit tests)
        if self.mock_executor:
            try:
                status_code, resp_data = self.mock_executor(target_url, api_key, payload_dict)
                if status_code == 200:
                    model_text = ""
                    try:
                        model_text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        model_text = "Received valid response from Gemini API."
                    return DestinationResult(
                        status="API_RESPONSE",
                        provider=self.provider_name,
                        message="Received response from Google Gemini API (gemini-1.5-flash).",
                        external_id=resp_data.get("responseId", "gemini-resp-id"),
                        response_payload={"model": DEFAULT_GEMINI_MODEL, "response_text": model_text, "raw": resp_data}
                    )
                else:
                    return DestinationResult(
                        status="NETWORK_ERROR",
                        provider=self.provider_name,
                        message=f"Gemini API returned HTTP {status_code}: {resp_data.get('error', {}).get('message', 'API Error')}",
                        error_code=f"HTTP_{status_code}"
                    )
            except Exception as e:
                return DestinationResult(
                    status="NETWORK_ERROR",
                    provider=self.provider_name,
                    message=f"Mock execution error: {e}",
                    error_code="MOCK_EXECUTION_FAILED"
                )

        # Real HTTP Execution Path
        try:
            payload_bytes = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(
                target_url,
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_bytes = resp.read()
                resp_dict = json.loads(resp_bytes.decode("utf-8"))

                model_text = ""
                try:
                    model_text = resp_dict["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    model_text = "Received response from Gemini API."

                return DestinationResult(
                    status="API_RESPONSE",
                    provider=self.provider_name,
                    message="Received response from Google Gemini API (gemini-1.5-flash).",
                    external_id=resp_dict.get("responseId"),
                    response_payload={"model": DEFAULT_GEMINI_MODEL, "response_text": model_text, "raw": resp_dict}
                )

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
                err_json = json.loads(error_body)
                err_msg = err_json.get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)

            status = "AUTH_REQUIRED" if e.code in (400, 401, 403) and ("API key" in err_msg or "API_KEY" in err_msg) else "NETWORK_ERROR"
            return DestinationResult(
                status=status,
                provider=self.provider_name,
                message=f"Gemini API HTTP {e.code} Error: {err_msg}",
                error_code=f"HTTP_{e.code}"
            )
        except urllib.error.URLError as e:
            return DestinationResult(
                status="NETWORK_ERROR",
                provider=self.provider_name,
                message=f"Network connection failed: {e.reason}",
                error_code="NETWORK_FAILURE"
            )
        except Exception as e:
            return DestinationResult(
                status="NETWORK_ERROR",
                provider=self.provider_name,
                message=f"Unexpected error communicating with Gemini API: {e}",
                error_code="UNEXPECTED_ERROR"
            )
