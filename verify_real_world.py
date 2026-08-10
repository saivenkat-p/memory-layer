"""
Verification script testing real-world user queries against stored memories.
"""

from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.ai.memory_assistant import AskMyMemoryAssistant


def run_verification():
    db = Database(":memory:")
    repo = ConversationRepository(db)
    hybrid_engine = HybridSearchEngine(repo)
    assistant = AskMyMemoryAssistant(hybrid_engine)

    # Seed source message
    c1 = Conversation(
        title="Smart Water Tank Monitoring System",
        source="ChatGPT",
        category="Startup Idea",
        tags=["IoT", "Water", "Automation"],
        messages=[
            Message(
                role="user",
                content="I don't want to climb the stairs to check whether the overhead tank is full. I want a system that shows the water level remotely and automatically stops the motor.",
                index=0,
            ),
            Message(
                role="assistant",
                content="You can build a prototype using an ESP32 microcontroller with an ultrasonic distance sensor and relay module.",
                index=1,
            ),
        ],
    )
    repo.save_conversation(c1)

    queries = [
        "The idea where I don't have to go upstairs to inspect something",
        "A system that lets me remotely know whether a household resource is sufficient.",
        "Automatically prevent overflow without manually checking the tank.",
        "I need to remotely monitor household supply without physically inspecting it.",
        "Quantum entanglement circuit.",
        "Childhood cricket memories.",
    ]

    print("\n================ REAL WORLD HYBRID SEARCH TEST RESULTS ================")
    for q in queries:
        results = hybrid_engine.search(q)
        print(f"\nQUERY: '{q}'")
        if results:
            top = results[0]
            print(f"  --> MATCHED: '{top.conversation_title}' (Score: {top.score}%)")
            print(f"      SNIPPET: \"{top.snippet}\"")
        else:
            print("  --> RESULT: No sufficiently relevant memory found.")
    print("=======================================================================\n")


if __name__ == "__main__":
    run_verification()
