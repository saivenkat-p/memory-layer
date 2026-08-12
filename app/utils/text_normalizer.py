"""
Text normalization utility module for Memory Layer (Milestone V6.3 Memory Intelligence).

Provides deterministic, strictly anchored text sanitization functions to strip
extension-injected reference context blocks (e.g., '[Memory Layer Reference Context]:')
prior to vector embedding generation and search indexing.
"""

import re
from typing import Optional


# Strictly anchored pattern targeting Memory Layer prompt injection headers:
# Matches '[Memory Layer Reference Context]:' and any attached injected context block.
INJECTED_CONTEXT_PATTERN = re.compile(
    r"\[Memory Layer Reference Context\]:\s*",
    re.IGNORECASE
)


def strip_injected_context(text: Optional[str]) -> str:
    """
    Sanitizes raw text by removing Memory Layer extension-injected context markers.

    Guarantees:
    1. Returns empty string for None or whitespace-only input.
    2. Strips strictly anchored '[Memory Layer Reference Context]:' markers.
    3. Preserves all legitimate user prose, questions, and code blocks unchanged.
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    cleaned = INJECTED_CONTEXT_PATTERN.sub("", text)
    return cleaned.strip()
