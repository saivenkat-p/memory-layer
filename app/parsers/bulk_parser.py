"""
Bulk Conversation Archive and File Parser.

Handles extracting and parsing:
1. ZIP archives containing multiple .json or .txt conversation exports.
2. Bulk JSON files (such as ChatGPT export `conversations.json`).
3. Single file uploads as a fallback list of 1 conversation.
"""

import io
import zipfile
from typing import List, Union
from app.models.schemas import Conversation
from app.parsers.base import ParsingError
from app.parsers.json_parser import JSONParser
from app.parsers.factory import get_parser_for_filename


class BulkParser:
    """
    Utility class to extract and parse multi-conversation exports or archives.
    """

    def parse_archive_or_file(
        self, content: Union[bytes, str], filename: str
    ) -> List[Conversation]:
        """
        Parses raw content (bytes or str) from a file or zip archive into a list of Conversations.

        Args:
            content: Raw file content (bytes for zip/binary uploads, or str).
            filename: Name of the uploaded file/archive.

        Returns:
            List of standardized Conversation objects.
        """
        conversations: List[Conversation] = []

        # 1. ZIP Archive Handling
        if filename.lower().endswith(".zip") or (isinstance(content, bytes) and content.startswith(b"PK\x03\x04")):
            if isinstance(content, str):
                content = content.encode("utf-8")
            
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        # Skip directory entries or hidden files
                        if name.endswith("/") or name.startswith("__MACOSX/") or name.startswith("."):
                            continue
                        
                        ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
                        if ext not in ["json", "txt", "md", "log"]:
                            continue

                        try:
                            file_bytes = zf.read(name)
                            file_basename = name.rsplit("/", 1)[-1]

                            # Handle bulk JSON inside zip (e.g. conversations.json)
                            if ext == "json":
                                json_parser = JSONParser()
                                bulk_convs = json_parser.parse_bulk(file_bytes, filename=file_basename)
                                if bulk_convs:
                                    conversations.extend(bulk_convs)
                                    continue

                            # Fallback single file parsing
                            parser = get_parser_for_filename(file_basename)
                            conv = parser.parse(file_bytes, filename=file_basename)
                            conversations.append(conv)
                        except Exception:
                            continue
            except zipfile.BadZipFile as e:
                raise ParsingError(f"Invalid ZIP archive file: {e}")

            return conversations

        # 2. Single Bulk JSON file (e.g. conversations.json)
        if filename.lower().endswith(".json"):
            json_parser = JSONParser()
            bulk_convs = json_parser.parse_bulk(content, filename=filename)
            if bulk_convs:
                return bulk_convs

        # 3. Standard single conversation file fallback
        parser = get_parser_for_filename(filename)
        conv = parser.parse(content, filename=filename)
        return [conv]
