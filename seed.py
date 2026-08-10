"""
Seed script to populate initial sample demo dataset into data/memory.db.
"""

import os
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.parsers.factory import parse_conversation_file


def seed():
    db = Database(os.path.join("data", "memory.db"))
    repo = ConversationRepository(db)

    samples = [
        ("data/sample_chatgpt.json", "sample_chatgpt.json", "Startup Idea", ["IoT", "Water", "Automation"], "Smart water tank monitoring project"),
        ("data/sample_chat.txt", "sample_chat.txt", "Learning", ["Quantum", "Python", "Physics"], "Qiskit quantum circuit notes"),
    ]

    for path, filename, cat, tags, desc in samples:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            conv = parse_conversation_file(content, filename)
            conv.category = cat
            conv.tags = tags
            conv.description = desc
            repo.save_conversation(conv)
            print(f"Saved: {conv.title} ({conv.source}) with {conv.message_count} messages.")


if __name__ == "__main__":
    seed()
