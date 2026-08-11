"""
JSON Conversation Parser module.

Supports:
1. Standard list of messages: [{"role": "user", "content": "..."}, ...]
2. Object with title & messages: {"title": "...", "messages": [...]}
3. OpenAI ChatGPT export structure: {"title": "...", "mapping": {...}}
"""

import json
from typing import Union, List, Dict, Any
from app.models.schemas import Conversation, Message
from app.parsers.base import BaseParser, ParsingError


class JSONParser(BaseParser):
    """Parses JSON formatted conversation files into standardized Conversation objects."""

    def parse(self, content: Union[str, bytes], filename: str = "conversation.json") -> Conversation:
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ParsingError(f"Failed to decode UTF-8 bytes: {e}")

        if not content or not content.strip():
            raise ParsingError("Empty file content provided.")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParsingError(f"Invalid JSON format: {e}")

        title = filename.rsplit(".", 1)[0].replace("_", " ").title()
        source = "JSON"
        messages: List[Message] = []
        original_date = None

        # Case 1: Root is a list
        if isinstance(data, list):
            # Check if elements are conversation objects (e.g. ChatGPT bulk export conversations.json)
            if data and isinstance(data[0], dict) and ("mapping" in data[0] or "messages" in data[0]):
                convs = self.parse_bulk(content, filename=filename)
                if convs:
                    return convs[0]
                raise ParsingError("No valid conversations parsed from JSON array.")
            # Otherwise, it's a list of message objects for a single conversation
            messages = self._parse_message_list(data)

        # Case 2: Root is a dict
        elif isinstance(data, dict):
            if "title" in data and isinstance(data["title"], str):
                title = data["title"]
            if "source" in data and isinstance(data["source"], str):
                source = data["source"]
            if "created_at" in data or "date" in data:
                original_date = str(data.get("created_at") or data.get("date"))

            # Subcase A: OpenAI ChatGPT Export mapping format
            if "mapping" in data and isinstance(data["mapping"], dict):
                messages = self._parse_chatgpt_mapping(data["mapping"])
                source = "ChatGPT"
            # Subcase B: Standard 'messages' key
            elif "messages" in data and isinstance(data["messages"], list):
                messages = self._parse_message_list(data["messages"])
            else:
                raise ParsingError("JSON dict does not contain 'messages' list or ChatGPT 'mapping'.")
        else:
            raise ParsingError("JSON root must be an array or an object.")

        if not messages:
            raise ParsingError("No valid conversation messages extracted from JSON.")

        return Conversation(
            title=title,
            messages=messages,
            source=source,
            original_date=original_date,
        )

    def parse_bulk(self, content: Union[str, bytes], filename: str = "conversations.json") -> List[Conversation]:
        """
        Parses a bulk JSON file (such as a ChatGPT export `conversations.json`) containing
        a list of multiple conversation objects. Returns a list of standardized `Conversation` objects.
        """
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ParsingError(f"Failed to decode UTF-8 bytes: {e}")

        if not content or not content.strip():
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParsingError(f"Invalid JSON format: {e}")

        conversations: List[Conversation] = []

        if isinstance(data, list):
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                try:
                    title = item.get("title") or f"Conversation {idx + 1}"
                    source = item.get("source") or "ChatGPT"
                    original_date = str(item.get("create_time") or item.get("created_at") or "")

                    if "mapping" in item and isinstance(item["mapping"], dict):
                        msgs = self._parse_chatgpt_mapping(item["mapping"])
                        source = "ChatGPT"
                    elif "messages" in item and isinstance(item["messages"], list):
                        msgs = self._parse_message_list(item["messages"])
                    else:
                        continue

                    if msgs:
                        conversations.append(
                            Conversation(
                                title=title,
                                messages=msgs,
                                source=source,
                                original_date=original_date if original_date else None,
                            )
                        )
                except Exception:
                    continue
        elif isinstance(data, dict):
            try:
                conv = self.parse(content, filename=filename)
                conversations.append(conv)
            except ParsingError:
                pass

        return conversations

    def _parse_message_list(self, raw_list: List[Any]) -> List[Message]:
        messages: List[Message] = []
        for idx, item in enumerate(raw_list):
            if not isinstance(item, dict):
                continue
            
            # Normalize role
            raw_role = item.get("role") or item.get("speaker") or item.get("author", {}).get("role") or "user"
            role = str(raw_role).lower().strip()
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "bot", "ai", "model", "system"]:
                role = "assistant" if role != "system" else "system"
            else:
                role = "user"

            # Normalize content
            raw_content = item.get("content") or item.get("text") or item.get("message")
            if isinstance(raw_content, list):  # ChatGPT multi-part content
                parts = []
                for p in raw_content:
                    if isinstance(p, str):
                        parts.append(p)
                    elif isinstance(p, dict) and "text" in p:
                        parts.append(str(p["text"]))
                content_str = "\n".join(parts)
            elif isinstance(raw_content, dict) and "parts" in raw_content:
                parts = raw_content["parts"]
                content_str = "\n".join([str(p) for p in parts if isinstance(p, str)])
            elif isinstance(raw_content, str):
                content_str = raw_content
            else:
                content_str = str(raw_content or "")

            if not content_str.strip():
                continue

            timestamp = item.get("timestamp") or item.get("created_at") or item.get("date")
            messages.append(
                Message(
                    role=role,
                    content=content_str.strip(),
                    index=len(messages),
                    timestamp=str(timestamp) if timestamp else None,
                )
            )
        return messages

    def _parse_chatgpt_mapping(self, mapping: Dict[str, Any]) -> List[Message]:
        # Walk node tree in order
        nodes = list(mapping.values())
        raw_msgs = []
        for node in nodes:
            msg_obj = node.get("message")
            if not msg_obj:
                continue
            author_role = msg_obj.get("author", {}).get("role")
            if author_role in ["user", "assistant", "system"]:
                content_parts = msg_obj.get("content", {}).get("parts", [])
                text = "\n".join([str(p) for p in content_parts if isinstance(p, str)])
                if text.strip():
                    raw_msgs.append({
                        "role": author_role,
                        "content": text,
                        "created_at": msg_obj.get("create_time")
                    })
        return self._parse_message_list(raw_msgs)
