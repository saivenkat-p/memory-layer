"""
LLM-Powered Structured Memory Extractor (Milestone V6.5-E3).

Provides a provider-agnostic LLM extraction pipeline implementing BaseMemoryExtractor.
Accepts any BaseLLMClient implementation (Gemini, Mock, etc.) via dependency injection.
"""

import json
import logging
import os
import socket
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from app.models.schemas import Conversation, Message, StructuredMemory
from app.services.memory_extractor import BaseMemoryExtractor

logger = logging.getLogger(__name__)

SYSTEM_EXTRACTION_PROMPT = """You are an expert Personal AI Memory Extraction Agent.
Analyze the provided multi-turn conversation and extract discrete, high-value structured memories.

TAXONOMY & QUALIFICATION RULES:
1. 'decision': An explicit architectural, technical, or product choice adopted by the user/team.
   - MANDATORY: Assistant suggestions alone are NOT decisions. There must be clear evidence of user adoption.
2. 'preference': An explicitly stated user constraint, habit, tooling preference, or work style.
   - MANDATORY: ONLY explicitly stated preferences qualify (e.g. "I can spend 10 hrs/day"). Do NOT infer unstated habits.
3. 'fact': A verified domain rule, platform behavior, or external truth useful beyond the immediate turn.
   - MANDATORY: Exclude transient UI errors, momentary states, or unverified claims.
4. 'project_goal': An explicit project milestone, learning objective, deliverable, or funding target.

NON-MEMORY RULES (MUST IGNORE & EXTRACT NOTHING):
- Conversational filler and acknowledgments ("see...", "perfect...", "got it").
- Unadopted assistant suggestions or hypothetical option rankings.
- Exploratory questioning, speculation, or brainstorming.
- Raw code dumps, scripts, and documentation templates.
- Repetitive prompt wrapper preambles.

PROVENANCE:
- Set 'start_msg_index' and 'end_msg_index' to the exact 0-indexed turns where the memory originated.
- Set 'source_message_ids' to the exact message IDs provided in the transcript turns.
- For multi-turn decision sequences (proposal -> response -> adoption), capture the entire turn span.

OUTPUT FORMAT:
Return a JSON array of objects strictly matching this schema:
[
  {
    "memory_type": "decision" | "preference" | "fact" | "project_goal",
    "content": "Concise declarative standalone sentence (<200 chars)",
    "start_msg_index": int,
    "end_msg_index": int,
    "source_message_ids": ["msg_id_1", "msg_id_2"],
    "confidence": float,
    "rationale": "Brief explanation under E2 rules"
  }
]
If no high-value memories meet the criteria, return an empty array: []
"""


class BaseLLMClient(ABC):
    """Abstract provider client interface for LLM JSON completions."""

    @abstractmethod
    def generate_json(self, system_instruction: str, user_prompt: str) -> str:
        """Executes LLM completion and returns raw JSON response string."""
        pass


class MockLLMClient(BaseLLMClient):
    """Mock LLM client for offline unit testing without network calls."""

    def __init__(self, default_response: str = "[]", response_map: Optional[Dict[str, str]] = None):
        self.default_response = default_response
        self.response_map = response_map or {}
        self.calls: List[Dict[str, str]] = []

    def generate_json(self, system_instruction: str, user_prompt: str) -> str:
        self.calls.append({"system_instruction": system_instruction, "user_prompt": user_prompt})
        for key, resp in self.response_map.items():
            if key in user_prompt:
                return resp
        return self.default_response


class GeminiLLMClient(BaseLLMClient):
    """
    Google Gemini REST API client.
    Communicates with Google GenAI API endpoint via urllib.request (zero external package dependencies).
    Reads API key securely from environment variable GEMINI_API_KEY.
    """

    TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3.7-flash",
        timeout: int = 90,
        max_retries: int = 2,
        backoff_factor: float = 2.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.last_metadata: Dict[str, Any] = {}

    def preflight_check(self) -> Tuple[bool, str]:
        """
        Executes a lightweight preflight verification:
        1. Verifies GEMINI_API_KEY is present.
        2. Verifies configured model is exactly 'gemini-3.7-flash'.
        3. Executes a minimal generateContent ping to verify API connectivity, model accessibility,
           and absence of 429 (quota) or 503 (high demand) blocking errors.
        Returns (success: bool, message: str).
        """
        if not self.api_key:
            return False, "GEMINI_API_KEY environment variable is not set or empty."

        if self.model != "gemini-3.7-flash":
            return False, f"Configured model '{self.model}' is invalid. Benchmark model must be exactly 'gemini-3.7-flash'."

        try:
            self.generate_json(
                system_instruction="Healthcheck",
                user_prompt="ping"
            )
            return True, f"Preflight check passed: model '{self.model}' is accessible and responsive."
        except Exception as e:
            return False, f"Preflight check failed: {e}"

    def generate_json(self, system_instruction: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Set GEMINI_API_KEY in your environment to execute live extraction."
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            }
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )

        attempts = 0
        max_attempts = 1 + self.max_retries
        last_error: Optional[Exception] = None

        while attempts < max_attempts:
            attempts += 1
            start_time = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    elapsed = time.time() - start_time
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)

                    # Capture token usage metadata if available
                    usage = res_json.get("usageMetadata", {})
                    self.last_metadata = {
                        "attempts": attempts,
                        "retries": attempts - 1,
                        "latency_seconds": round(elapsed, 2),
                        "status_code": 200,
                        "prompt_tokens": usage.get("promptTokenCount"),
                        "candidates_tokens": usage.get("candidatesTokenCount"),
                        "total_tokens": usage.get("totalTokenCount"),
                    }

                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        return "[]"
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        return "[]"
                    return parts[0].get("text", "[]")

            except urllib.error.HTTPError as e:
                elapsed = time.time() - start_time
                err_msg = e.read().decode("utf-8")
                last_error = RuntimeError(f"Gemini API error ({e.code}): {err_msg}")
                logger.error(f"Gemini API HTTPError {e.code} on attempt {attempts}/{max_attempts}: {err_msg}")

                if e.code in self.TRANSIENT_HTTP_CODES and attempts < max_attempts:
                    sleep_time = self.backoff_factor ** (attempts - 1)
                    logger.info(f"Transient HTTP {e.code}. Retrying in {sleep_time:.1f}s (attempt {attempts+1}/{max_attempts})...")
                    time.sleep(sleep_time)
                    continue
                else:
                    self.last_metadata = {
                        "attempts": attempts,
                        "retries": attempts - 1,
                        "latency_seconds": round(elapsed, 2),
                        "status_code": e.code,
                        "error": str(last_error),
                    }
                    raise last_error from e

            except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
                elapsed = time.time() - start_time
                last_error = RuntimeError(f"Gemini API request failed (transient network/timeout): {e}")
                logger.error(f"Gemini network/timeout error on attempt {attempts}/{max_attempts}: {e}")

                if attempts < max_attempts:
                    sleep_time = self.backoff_factor ** (attempts - 1)
                    logger.info(f"Transient network error. Retrying in {sleep_time:.1f}s (attempt {attempts+1}/{max_attempts})...")
                    time.sleep(sleep_time)
                    continue
                else:
                    self.last_metadata = {
                        "attempts": attempts,
                        "retries": attempts - 1,
                        "latency_seconds": round(elapsed, 2),
                        "status_code": None,
                        "error": str(last_error),
                    }
                    raise last_error from e

            except Exception as e:
                elapsed = time.time() - start_time
                last_error = RuntimeError(f"Gemini API unexpected request failed: {e}")
                logger.error(f"Gemini unhandled exception on attempt {attempts}/{max_attempts}: {e}")
                self.last_metadata = {
                    "attempts": attempts,
                    "retries": attempts - 1,
                    "latency_seconds": round(elapsed, 2),
                    "status_code": None,
                    "error": str(last_error),
                }
                raise last_error from e

        if last_error:
            raise last_error
        return "[]"


class LLMMemoryExtractor(BaseMemoryExtractor):
    """
    LLM-powered memory extractor enforcing E2 taxonomy, schema validation,
    candidate budgeting, and provenance checks.
    """

    ALLOWED_TYPES = {"decision", "preference", "fact", "project_goal"}
    MAX_CANDIDATES = 5

    def __init__(self, client: BaseLLMClient, max_candidates: int = MAX_CANDIDATES):
        self.client = client
        self.max_candidates = max_candidates

    def build_prompt(self, conversation: Conversation) -> str:
        """Formats conversation transcript turns into a structured prompt."""
        lines = [
            f"=== CONVERSATION METADATA ===",
            f"Title: {conversation.title}",
            f"Source: {conversation.source}",
            f"Total Messages: {len(conversation.messages)}",
            "",
            f"=== TRANSCRIPT TURNS ===",
        ]

        for m in conversation.messages:
            lines.append(f"[Turn {m.index}] ({m.role}) ID: {m.id}")
            lines.append(f"Content:\n{m.content}")
            lines.append("-" * 40)

        return "\n".join(lines)

    def extract_memories(self, conversation: Conversation) -> List[StructuredMemory]:
        """
        Executes LLM extraction, validates schema and provenance, enforces candidate budget,
        and returns validated StructuredMemory instances.
        """
        if not conversation.messages:
            return []

        user_prompt = self.build_prompt(conversation)

        try:
            raw_response = self.client.generate_json(SYSTEM_EXTRACTION_PROMPT, user_prompt)
        except Exception as e:
            logger.error(f"LLM extraction call failed for conversation '{conversation.title}': {e}")
            return []

        # Parse JSON
        try:
            cleaned_text = raw_response.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            parsed_data = json.loads(cleaned_text) if cleaned_text else []
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON response for conversation '{conversation.title}': {e} | Raw: {raw_response[:200]}")
            return []

        if not isinstance(parsed_data, list):
            logger.warning(f"LLM response for conversation '{conversation.title}' was not a JSON list.")
            return []

        # Map messages by index and ID for provenance validation
        msgs_by_index = {m.index: m for m in conversation.messages}
        msgs_by_id = {m.id: m for m in conversation.messages}

        validated_memories: List[StructuredMemory] = []

        for item in parsed_data:
            if not isinstance(item, dict):
                continue

            mem_type = str(item.get("memory_type", "")).strip().lower()
            if mem_type not in self.ALLOWED_TYPES:
                logger.warning(f"Rejected invalid memory_type '{mem_type}' for conversation '{conversation.title}'")
                continue

            content = str(item.get("content", "")).strip()
            if not content:
                continue

            start_idx = item.get("start_msg_index")
            end_idx = item.get("end_msg_index")
            source_ids = item.get("source_message_ids")

            # Validate indices
            if not isinstance(start_idx, int) or not isinstance(end_idx, int):
                logger.warning(f"Rejected candidate with non-integer turn indices: start={start_idx}, end={end_idx}")
                continue

            if start_idx < 0 or end_idx < start_idx or end_idx >= len(conversation.messages):
                logger.warning(f"Rejected candidate with invalid index range [{start_idx}, {end_idx}] (conv length: {len(conversation.messages)})")
                continue

            # Validate source_message_ids
            if not isinstance(source_ids, list) or not source_ids:
                logger.warning(f"Rejected candidate with missing/invalid source_message_ids: {source_ids}")
                continue

            # Provenance Check: Verify every message ID exists in the conversation within the declared range
            valid_ids = True
            for mid in source_ids:
                if mid not in msgs_by_id:
                    logger.warning(f"Rejected candidate with hallucinated message ID '{mid}'")
                    valid_ids = False
                    break
                msg_obj = msgs_by_id[mid]
                if not (start_idx <= msg_obj.index <= end_idx):
                    logger.warning(f"Rejected candidate where message '{mid}' (index {msg_obj.index}) is outside declared range [{start_idx}, {end_idx}]")
                    valid_ids = False
                    break

            if not valid_ids:
                continue

            confidence = float(item.get("confidence", 1.0))

            validated_memories.append(
                StructuredMemory(
                    conversation_id=conversation.id,
                    memory_type=mem_type,
                    content=content,
                    start_msg_index=start_idx,
                    end_msg_index=end_idx,
                    source_message_ids=source_ids,
                    provider=conversation.source,
                    confidence=confidence,
                    status="active"
                )
            )

        # Enforce candidate budget
        if len(validated_memories) > self.max_candidates:
            logger.info(f"Enforcing candidate budget on '{conversation.title}': capping {len(validated_memories)} candidates to {self.max_candidates}")
            validated_memories = validated_memories[:self.max_candidates]

        return validated_memories
