"""
Parser Factory module.
Selects the appropriate parser strategy based on filename extension or content inspection.
"""

from typing import Union
from app.models.schemas import Conversation
from app.parsers.base import BaseParser, ParsingError
from app.parsers.json_parser import JSONParser
from app.parsers.txt_parser import TXTParser


def get_parser_for_filename(filename: str) -> BaseParser:
    """
    Selects and returns an initialized BaseParser instance based on file extension.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "json":
        return JSONParser()
    elif ext in ["txt", "md", "log"]:
        return TXTParser()
    else:
        # Default fallback attempt
        return TXTParser()


def parse_conversation_file(content: Union[str, bytes], filename: str) -> Conversation:
    """
    High-level utility function to parse any supported conversation file.

    Args:
        content: Raw text string or raw byte string.
        filename: Name of the uploaded file.

    Returns:
        Standardized Conversation dataclass instance.
    """
    parser = get_parser_for_filename(filename)
    try:
        return parser.parse(content, filename=filename)
    except ParsingError:
        # If JSON parser fails on .json file, attempt TXT parser fallback
        if isinstance(parser, JSONParser):
            return TXTParser().parse(content, filename=filename)
        raise
