"""
Unit tests for `app/utils/text_normalizer.py` (Milestone V6.3 Memory Intelligence).
"""

import unittest
from app.utils.text_normalizer import strip_injected_context


class TestTextNormalizer(unittest.TestCase):
    """Test suite verifying strict context stripping and text normalization."""

    def test_01_strip_injected_context_marker(self):
        """TEST 01: Injected context header is stripped cleanly."""
        raw = "[Memory Layer Reference Context]:\nHere is prior context from chat.\n\nHow do I deploy this?"
        cleaned = strip_injected_context(raw)
        self.assertNotIn("[Memory Layer Reference Context]:", cleaned)
        self.assertTrue(cleaned.endswith("How do I deploy this?"))

    def test_02_normal_user_text_unchanged(self):
        """TEST 02: Normal user questions and code blocks are unchanged."""
        raw = "What is the Grover search algorithm complexity?\ndef test(): pass"
        cleaned = strip_injected_context(raw)
        self.assertEqual(cleaned, raw)

    def test_03_similar_non_marker_text_unchanged(self):
        """TEST 03: Similar phrasing not matching exact marker is preserved."""
        raw = "In this context, reference layers help memory."
        cleaned = strip_injected_context(raw)
        self.assertEqual(cleaned, raw)

    def test_04_empty_and_none_handling(self):
        """TEST 04: None, empty string, and whitespace return empty string."""
        self.assertEqual(strip_injected_context(None), "")
        self.assertEqual(strip_injected_context(""), "")
        self.assertEqual(strip_injected_context("   \n\t  "), "")


if __name__ == "__main__":
    unittest.main()
