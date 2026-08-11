"""
Gemini (Google AI Interactions API) Destination Adapter (Milestone V5B: Live AI Integration).

Migrates from legacy generateContent to official Google Interactions API standard:
1. Endpoint: POST https://generativelanguage.googleapis.com/v1beta/interactions?key={API_KEY}
2. Model: gemini-3.6-flash
3. Flat payload: {"model": "gemini-3.6-flash", "system_instruction": "...", "input": "..."}
4. Response parsing: extracts text from output_text, steps array, output, or fallback.
5. Transmits ONLY user-selected package messages (never full SQLite DB).
6. Supports environment variable (GEMINI_API_KEY) or UI configuration without logging secrets.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, Optional, List

from app.models.schemas import PortableContextPackage
from app.services.destination_adapters.base import DestinationAdapter, DestinationResult

logger = logging.getLogger(__name__)

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class GeminiAdapter(DestinationAdapter):
    """
    Concrete Destination Adapter for official Google Gemini Interactions API (gemini-3.6-flash).
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

        # Check API Key safely
        config_dict = config if isinstance(config, dict) else {}
        raw_key = config_dict.get("api_key")
        if not raw_key or not isinstance(raw_key, str) or not raw_key.strip():
            raw_key = os.environ.get("GEMINI_API_KEY", "")

        api_key = raw_key.strip()
        if not api_key:
            return DestinationResult(
                status="AUTH_REQUIRED",
                provider=self.provider_name,
                message="Missing GEMINI_API_KEY credential. Please set GEMINI_API_KEY environment variable or enter key in settings.",
                error_code="MISSING_API_KEY"
            )

        # Guard against query/topic string accidentally passed as API key
        if any(c in api_key for c in (" ", "\n", "\r", "\t")) or (package and (api_key == package.topic or api_key == package.topic.strip())):
            return DestinationResult(
                status="AUTH_REQUIRED",
                provider=self.provider_name,
                message="Invalid GEMINI_API_KEY format. API key cannot contain spaces, newlines, or query text.",
                error_code="INVALID_API_KEY_FORMAT"
            )

        return DestinationResult(
            status="SUCCESS",
            provider=self.provider_name,
            message="Package and credentials validated for Google Gemini Interactions API transmission."
        )

    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        """
        Transforms PortableContextPackage v1.0 into flat Gemini Interactions API payload:
        - model: "gemini-3.6-flash"
        - system_instruction: tags historical context.
        - input: formatted prompt containing ordered messages.
        """
        if not package or not package.messages:
            raise ValueError("Invalid package for Gemini preparation.")

        conv_titles = ", ".join(c.get("title", "") for c in package.source_conversations)

        system_instruction = (
            "You are an AI assistant. The user is providing historical reference context retrieved from their "
            "Personal AI Memory Layer across past conversations.\n"
            f"Topic / Goal: {package.topic}\n"
            f"Source Conversations ({len(package.source_conversations)}): {conv_titles}\n"
            "IMPORTANT: Treat the following user and model messages as historical reference material from past sessions, "
            "not as direct prior outputs in this current active session. Use this context to assist the user with their current objective."
        )

        input_parts = []
        for msg in package.messages:
            role_tag = f"[{msg.get('role', 'user').title()}]"
            prov_info = f"[Historical Context - Provider: {msg.get('provider', 'Unknown')} | Conv: {msg.get('conversation_title', '')}]"
            input_parts.append(f"{role_tag} {prov_info}\n{msg.get('content', '').strip()}")

        input_text = "\n\n".join(input_parts)

        return {
            "model": DEFAULT_GEMINI_MODEL,
            "system_instruction": system_instruction,
            "input": input_text,
        }

    def _extract_response_text(self, resp_dict: Dict[str, Any]) -> str:
        """Helper to extract response text from Interactions API payload or fallbacks."""
        if "output_text" in resp_dict and isinstance(resp_dict["output_text"], str):
            return resp_dict["output_text"]

        if "steps" in resp_dict and isinstance(resp_dict["steps"], list) and len(resp_dict["steps"]) > 0:
            step_outputs = []
            for step in resp_dict["steps"]:
                if isinstance(step, dict):
                    if "output_text" in step:
                        step_outputs.append(str(step["output_text"]))
                    elif "output" in step:
                        step_outputs.append(str(step["output"]))
                    elif "text" in step:
                        step_outputs.append(str(step["text"]))
            if step_outputs:
                return "\n".join(step_outputs)

        if "output" in resp_dict and isinstance(resp_dict["output"], str):
            return resp_dict["output"]

        # Legacy candidate fallback if provider proxies generateContent format
        if "candidates" in resp_dict and isinstance(resp_dict["candidates"], list) and len(resp_dict["candidates"]) > 0:
            try:
                return resp_dict["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                pass

        return "Received response from Gemini Interactions API."

    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        """
        Executes transmission to Google Gemini Interactions API.
        """
        val_res = self.validate(package, config)
        if val_res.status != "SUCCESS":
            return val_res

        config_dict = config if isinstance(config, dict) else {}
        raw_key = config_dict.get("api_key")
        if not raw_key or not isinstance(raw_key, str) or not raw_key.strip():
            raw_key = os.environ.get("GEMINI_API_KEY", "")

        api_key = raw_key.strip()
        encoded_key = urllib.parse.quote(api_key)

        payload_dict = self.prepare(package)
        target_url = f"{GEMINI_API_ENDPOINT}?key={encoded_key}"

        # Mock Execution Path (Used during automated unit tests)
        if self.mock_executor:
            try:
                status_code, resp_data = self.mock_executor(target_url, api_key, payload_dict)
                if status_code == 200:
                    model_text = self._extract_response_text(resp_data)
                    return DestinationResult(
                        status="API_RESPONSE",
                        provider=self.provider_name,
                        message=f"Received response from Google Gemini API ({DEFAULT_GEMINI_MODEL}).",
                        external_id=resp_data.get("id", resp_data.get("responseId", "gemini-resp-id")),
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
                model_text = self._extract_response_text(resp_dict)

                return DestinationResult(
                    status="API_RESPONSE",
                    provider=self.provider_name,
                    message=f"Received response from Google Gemini API ({DEFAULT_GEMINI_MODEL}).",
                    external_id=resp_dict.get("id", resp_dict.get("responseId")),
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
