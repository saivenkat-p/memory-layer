"""
Base Parser Interface and Custom Parsing Exceptions.
"""

from abc import ABC, abstractmethod
from typing import Union
from app.models.schemas import Conversation


class ParsingError(Exception):
    """Raised when parsing a conversation file fails due to malformed data or unsupported structure."""
    pass


class BaseParser(ABC):
    """
    Abstract Base Class for all conversation parsers.
    Any new provider parser (JSON, TXT, CSV, PDF) must inherit from this class
    and implement the `parse` method.
    """

    @abstractmethod
    def parse(self, content: Union[str, bytes], filename: str = "conversation") -> Conversation:
        """
        Parse raw content string or bytes into a standardized `Conversation` instance.

        Args:
            content: The raw text or file bytes.
            filename: The name of the file being parsed (useful for title fallbacks).

        Returns:
            Conversation schema instance populated with extracted messages.

        Raises:
            ParsingError: If content cannot be parsed.
        """
        pass
