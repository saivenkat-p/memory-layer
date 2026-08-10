"""
Unit test suite for Conversation Parsers (JSON & TXT) using standard library unittest.
"""

import unittest
from app.parsers.factory import parse_conversation_file
from app.parsers.base import ParsingError
from app.parsers.json_parser import JSONParser
from app.parsers.txt_parser import TXTParser


class TestConversationParsers(unittest.TestCase):

    def test_parse_sample_json(self):
        with open("data/sample_chatgpt.json", "r", encoding="utf-8") as f:
            content = f.read()

        conv = parse_conversation_file(content, "sample_chatgpt.json")

        self.assertEqual(conv.title, "Smart Water Tank IoT Monitoring Idea")
        self.assertEqual(conv.source, "ChatGPT")
        self.assertEqual(conv.message_count, 4)
        self.assertEqual(conv.messages[0].role, "user")
        self.assertIn("water tank", conv.messages[0].content.lower())
        self.assertEqual(conv.messages[1].role, "assistant")
        self.assertIn("ESP32", conv.messages[1].content)

    def test_parse_sample_txt(self):
        with open("data/sample_chat.txt", "r", encoding="utf-8") as f:
            content = f.read()

        conv = parse_conversation_file(content, "sample_chat.txt")

        self.assertEqual(conv.title, "Sample Chat")
        self.assertEqual(conv.source, "TXT")
        self.assertEqual(conv.message_count, 4)
        self.assertEqual(conv.messages[0].role, "user")
        self.assertIn("Qiskit", conv.messages[0].content)
        self.assertEqual(conv.messages[1].role, "assistant")
        self.assertIn("QuantumCircuit", conv.messages[1].content)

    def test_empty_content_raises_error(self):
        with self.assertRaises(ParsingError):
            parse_conversation_file("", "empty.json")

        with self.assertRaises(ParsingError):
            parse_conversation_file("   \n ", "empty.txt")

    def test_malformed_json_raises_error(self):
        malformed_json = '{"title": "Broken", "messages": ['
        with self.assertRaises(ParsingError):
            JSONParser().parse(malformed_json, "broken.json")

    def test_chatgpt_mapping_format(self):
        chatgpt_export = """
        {
            "title": "ChatGPT Export Test",
            "mapping": {
                "node-1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Hello AI"]}
                    }
                },
                "node-2": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Hello Human"]}
                    }
                }
            }
        }
        """
        conv = JSONParser().parse(chatgpt_export, "chatgpt_export.json")
        self.assertEqual(conv.title, "ChatGPT Export Test")
        self.assertEqual(conv.source, "ChatGPT")
        self.assertEqual(conv.message_count, 2)
        self.assertEqual(conv.messages[0].content, "Hello AI")
        self.assertEqual(conv.messages[1].content, "Hello Human")


if __name__ == "__main__":
    unittest.main()
