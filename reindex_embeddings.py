"""
CLI tool to re-index all stored conversations and messages using the active embedding model.
Replaces stale or legacy embeddings in data/memory.db.
"""

import os
import sys
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.semantic_search import SemanticSearchEngine, ACTIVE_MODEL_NAME


def main():
    db_path = os.path.join("data", "memory.db")
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}.")
        sys.exit(1)

    print(f"================ RE-INDEXING VECTOR EMBEDDINGS ================")
    print(f"Target Database : {os.path.abspath(db_path)}")
    print(f"Active Model    : {ACTIVE_MODEL_NAME}")
    print("Initializing model weights & processing database...")

    db = Database(db_path)
    repo = ConversationRepository(db)
    semantic_engine = SemanticSearchEngine(repo)

    stats = semantic_engine.reindex_all_embeddings()

    print("\n---------------- RE-INDEXING SUMMARY ----------------")
    print(f"Embedding model        : {stats['model_name']}")
    print(f"Conversations found    : {stats['conversations_found']}")
    print(f"Messages found         : {stats['messages_found']}")
    print(f"Embeddings regenerated : {stats['embeddings_reindexed']}")
    print(f"Failures               : {stats['failures']}")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
