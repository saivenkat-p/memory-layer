"""
TXT Conversation Parser module.

Supports plain text chat logs with speaker headers such as:
- 'User: ...', 'Assistant: ...', 'AI: ...', 'Human: ...'
- '**User**: ...', '**Assistant**: ...'
- '[Timestamp] Speaker: ...'
"""

import re
from typing import Union, List
from app.models.schemas import Conversation, Message
from app.parsers.base import BaseParser, ParsingError


class TXTParser(BaseParser):
    """Parses plain text chat transcripts into standardized Conversation objects."""

    # Regex patterns for detecting speaker boundaries
    SPEAKER_PATTERN = re.compile(
        r'^(?:\[(?P<timestamp>[^\]]+)\]\s*)?'  # Optional timestamp [2026-08-10 ...]
        r'(?:\*\*)?(?P<speaker>User|Human|Assistant|AI|ChatGPT|Claude|Gemini|Perplexity|System|Bot)(?:\*\*)?'
        r'\s*:\s*(?P<text>.*)$',
        re.IGNORECASE
    )

    def parse(self, content: Union[str, bytes], filename: str = "conversation.txt") -> Conversation:
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ParsingError(f"Failed to decode UTF-8 bytes: {e}")

        if not content or not content.strip():
            raise ParsingError("Empty file content provided.")

        lines = content.splitlines()
        title = filename.rsplit(".", 1)[0].replace("_", " ").title()
        messages: List[Message] = []

        current_role = None
        current_speaker_name = None
        current_timestamp = None
        current_text_lines: List[str] = []

        def flush_message():
            nonlocal current_role, current_text_lines, current_timestamp
            if current_role and current_text_lines:
                full_text = "\n".join(current_text_lines).strip()
                if full_text:
                    messages.append(
                        Message(
                            role=current_role,
                            content=full_text,
                            index=len(messages),
                            timestamp=current_timestamp,
                        )
                    )
            current_text_lines = []

        for line in lines:
            match = self.SPEAKER_PATTERN.match(line.strip())
            if match:
                # Flush previous message block
                flush_message()

                speaker_raw = match.group("speaker").lower()
                current_timestamp = match.group("timestamp")
                
                if speaker_raw in ["user", "human"]:
                    current_role = "user"
                elif speaker_raw in ["assistant", "ai", "chatgpt", "claude", "gemini", "perplexity", "bot"]:
                    current_role = "assistant"
                elif speaker_raw == "system":
                    current_role = "system"
                else:
                    current_role = "user"

                first_text = match.group("text")
                if first_text:
                    current_text_lines.append(first_text)
            else:
                # Continuation line of current message or fallback
                if current_role is not None:
                    current_text_lines.append(line)
                else:
                    # Header line or un-tagged initial line - treat as user message fallback if not empty
                    if line.strip():
                        current_role = "user"
                        current_text_lines.append(line)

        # Flush final message block
        flush_message()

        if not messages:
            raise ParsingError("Could not extract any valid messages from text file.")

        return Conversation(
            title=title,
            messages=messages,
            source="TXT",
        )
