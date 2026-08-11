"""
Bulk Import Engine Service.

Coordinates extracting, parsing, duplicate checking, saving, and embedding generation
for multi-conversation exports and archives with real-time progress callbacks and metrics reporting.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Union, Callable, Optional, Dict, Any

from app.models.schemas import Conversation
from app.parsers.bulk_parser import BulkParser
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine

logger = logging.getLogger(__name__)


@dataclass
class BulkImportResult:
    """Dataclass holding summary metrics for a bulk import operation."""
    conversations_detected: int = 0
    conversations_imported: int = 0
    duplicates_skipped: int = 0
    messages_imported: int = 0
    embeddings_generated: int = 0
    failures: int = 0
    skipped_items: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversations_detected": self.conversations_detected,
            "conversations_imported": self.conversations_imported,
            "duplicates_skipped": self.duplicates_skipped,
            "messages_imported": self.messages_imported,
            "embeddings_generated": self.embeddings_generated,
            "failures": self.failures,
            "skipped_items": self.skipped_items,
        }


ProgressCallback = Callable[[int, int, str], None]


class BulkImportEngine:
    """
    Engine that manages multi-conversation history ingestion, duplicate prevention,
    batch database storage, progress notification, and neural embedding generation.
    """

    def __init__(self, repo: Optional[ConversationRepository] = None):
        self.repo = repo or ConversationRepository()
        self.bulk_parser = BulkParser()

    def import_archive_or_file(
        self,
        content: Union[bytes, str],
        filename: str,
        progress_callback: Optional[ProgressCallback] = None,
        skip_duplicates: bool = True,
    ) -> BulkImportResult:
        """
        Parses and ingests conversations from an uploaded archive or bulk export file.

        Args:
            content: Raw file content bytes or string.
            filename: Name of the uploaded file/archive.
            progress_callback: Optional callable `(current, total, status_str) -> None`.
            skip_duplicates: If True, skips conversations that already exist in the database.

        Returns:
            BulkImportResult summary.
        """
        result = BulkImportResult()

        if progress_callback:
            progress_callback(0, 0, f"Extracting conversations from '{filename}'...")

        # 1. Extract & parse conversations from file/archive
        try:
            parsed_convs = self.bulk_parser.parse_archive_or_file(content, filename)
        except Exception as e:
            logger.error(f"Failed to parse archive/file '{filename}': {e}")
            result.failures += 1
            result.skipped_items.append(f"{filename}: Parse Error - {e}")
            return result

        result.conversations_detected = len(parsed_convs)
        if result.conversations_detected == 0:
            if progress_callback:
                progress_callback(0, 0, "No valid conversations found in export file.")
            return result

        # 2. Process each conversation with progress updates
        for idx, conv in enumerate(parsed_convs, start=1):
            status_prefix = f"Processing conversation {idx} of {result.conversations_detected}: '{conv.title}'"
            if progress_callback:
                progress_callback(idx, result.conversations_detected, status_prefix)

            # Duplicate Check
            if skip_duplicates and self.repo.is_duplicate(conv):
                result.duplicates_skipped += 1
                result.skipped_items.append(f"Skipped duplicate: '{conv.title}'")
                logger.info(f"Skipping duplicate conversation '{conv.title}'")
                continue

            try:
                # Save conversation and trigger vector embedding generation
                self.repo.save_conversation(conv)
                result.conversations_imported += 1
                result.messages_imported += conv.message_count
                result.embeddings_generated += conv.message_count
            except Exception as e:
                logger.error(f"Failed to ingest conversation '{conv.title}': {e}")
                result.failures += 1
                result.skipped_items.append(f"Failed: '{conv.title}' - {e}")

        if progress_callback:
            progress_callback(
                result.conversations_detected,
                result.conversations_detected,
                f"Import complete! {result.conversations_imported} imported, {result.duplicates_skipped} duplicates skipped.",
            )

        return result
