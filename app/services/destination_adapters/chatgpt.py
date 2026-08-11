"""
ChatGPT (OpenAI API) Destination Adapter (Milestone V5B: Live AI Integration).

Transforms a PortableContextPackage into native multi-turn messages array for official OpenAI Chat API:
1. Clearly distinguishes historical reference context from active session model outputs in system prompt.
2. Preserves ordered multi-turn structure of package.messages.
3. Transmits ONLY the user-selected package messages (never full SQLite DB).
4. Supports environment variable (OPENAI_API_KEY) or UI configuration without logging secrets.
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

OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


class ChatGPTAdapter(DestinationAdapter):
    """
    Concrete Destination Adapter for official OpenAI Chat API (ChatGPT).
    """

    def __init__(self, mock_executor: Optional[Any] = None):
        """
        Args:
            mock_executor: Optional mock callable `(url, headers, payload_bytes) -> (status_code, response_dict)`
                           used for unit testing to avoid real HTTP network calls.
        """
        self.mock_executor = mock_executor

    @property
    def provider_name(self) -> str:
        return "ChatGPT (OpenAI API)"

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
        api_key = config_dict.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key or not str(api_key).strip():
            return DestinationResult(
                status="AUTH_REQUIRED",
                provider=self.provider_name,
                message="Missing OPENAI_API_KEY credential. Please set OPENAI_API_KEY environment variable or enter key in settings.",
                error_code="MISSING_API_KEY"
            )

        return DestinationResult(
            status="SUCCESS",
            provider=self.provider_name,
            message="Package and credentials validated for OpenAI API transmission."
        )

    def prepare(self, package: PortableContextPackage) -> Dict[str, Any]:
        """
        Transforms PortableContextPackage v1.0 into native OpenAI Chat Completions payload:
        - Clearly tags historical context in system prompt.
        - Preserves ordered multi-turn structure (user/assistant).
        """
        if not package or not package.messages:
            raise ValueError("Invalid package for OpenAI preparation.")

        conv_titles = ", ".join(c.get("title", "") for c in package.source_conversations)
        
        system_content = (
            "You are an AI assistant. The user is providing historical reference context retrieved from their "
            "Personal AI Memory Layer across past conversations.\n"
            f"Topic / Goal: {package.topic}\n"
            f"Source Conversations ({len(package.source_conversations)}): {conv_titles}\n"
            "IMPORTANT: Treat the following user and assistant messages as historical reference material from past sessions, "
            "not as direct prior outputs in this current active session. Use this context to assist the user with their current objective."
        )

        formatted_messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]

        for msg in package.messages:
            role = "user" if msg.get("role") == "user" else "assistant"
            prov_info = f"[Historical Context - Provider: {msg.get('provider', 'Unknown')} | Conv: {msg.get('conversation_title', '')}]"
            msg_text = f"{prov_info}\n{msg.get('content', '')}"
            formatted_messages.append({
                "role": role,
                "content": msg_text
            })

        return {
            "model": DEFAULT_MODEL,
            "messages": formatted_messages,
            "temperature": 0.7,
        }

    def execute(self, package: PortableContextPackage, config: Optional[Dict[str, Any]] = None) -> DestinationResult:
        """
        Executes transmission to OpenAI Chat API.
        """
        val_res = self.validate(package, config)
        if val_res.status != "SUCCESS":
            return val_res

        config_dict = config or {}
        api_key = config_dict.get("api_key") or os.environ.get("OPENAI_API_KEY")
        model = config_dict.get("model", DEFAULT_MODEL)

        payload_dict = self.prepare(package)
        payload_dict["model"] = model

        # Mock Execution Path (Used during automated unit tests)
        if self.mock_executor:
            try:
                status_code, resp_data = self.mock_executor(OPENAI_CHAT_ENDPOINT, api_key, payload_dict)
                if status_code == 200:
                    assistant_msg = ""
                    try:
                        assistant_msg = resp_data["choices"][0]["message"]["content"]
                    except Exception:
                        assistant_msg = "Received valid response from OpenAI API."
                    return DestinationResult(
                        status="API_RESPONSE",
                        provider=self.provider_name,
                        message=f"Received response from OpenAI API ({model}).",
                        external_id=resp_data.get("id"),
                        response_payload={"model": model, "response_text": assistant_msg, "raw": resp_data}
                    )
                else:
                    return DestinationResult(
                        status="NETWORK_ERROR",
                        provider=self.provider_name,
                        message=f"OpenAI API returned HTTP {status_code}: {resp_data.get('error', {}).get('message', 'API Error')}",
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
                OPENAI_CHAT_ENDPOINT,
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key.strip()}"
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_bytes = resp.read()
                resp_dict = json.loads(resp_bytes.decode("utf-8"))
                
                assistant_text = ""
                try:
                    assistant_text = resp_dict["choices"][0]["message"]["content"]
                except Exception:
                    assistant_text = "Received response from OpenAI API."

                return DestinationResult(
                    status="API_RESPONSE",
                    provider=self.provider_name,
                    message=f"Received response from OpenAI API ({model}).",
                    external_id=resp_dict.get("id"),
                    response_payload={"model": model, "response_text": assistant_text, "raw": resp_dict}
                )

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
                err_json = json.loads(error_body)
                err_msg = err_json.get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)

            status = "AUTH_REQUIRED" if e.code in (401, 403) else "NETWORK_ERROR"
            return DestinationResult(
                status=status,
                provider=self.provider_name,
                message=f"OpenAI API HTTP {e.code} Error: {err_msg}",
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
                message=f"Unexpected error communicating with OpenAI API: {e}",
                error_code="UNEXPECTED_ERROR"
            )
