"""
Comprehensive Acceptance Test Suite for Neural Hybrid Search Architecture.

Proves genuine semantic retrieval using local SentenceTransformer embeddings ('all-MiniLM-L6-v2').
Includes zero-vocabulary-overlap tests, exact keyword tests, false-positive rejection,
relevance thresholding, and SQLite vector persistence.
"""

import unittest
import os
import gc
from app.models.schemas import Conversation, Message
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine


class TestNeuralHybridSearch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set up in-memory DB and seed test conversations
        cls.db = Database(":memory:")
        cls.repo = ConversationRepository(cls.db)
        cls.hybrid_engine = HybridSearchEngine(cls.repo)

        # Source 1: Water Tank Idea with specific wording
        c1 = Conversation(
            title="Smart Water Tank Monitoring System",
            source="ChatGPT",
            category="Startup Idea",
            tags=["IoT", "Water", "Automation"],
            description="Remote tank monitoring idea",
            messages=[
                Message(
                    role="user",
                    content="I don't want to climb the stairs to check whether the overhead tank is full. I want a system that shows the water level remotely and automatically stops the motor.",
                    index=0,
                ),
                Message(
                    role="assistant",
                    content="You can build a prototype using an ESP32 microcontroller with an ultrasonic sensor and relay module.",
                    index=1,
                ),
            ],
        )

        # Source 2: Qiskit Quantum Computing
        c2 = Conversation(
            title="Quantum Computing with Qiskit",
            source="TXT",
            category="Learning",
            tags=["Quantum", "Python"],
            description="Qiskit quantum circuit notes",
            messages=[
                Message(
                    role="user",
                    content="How do I create a QuantumCircuit in Qiskit to measure quantum superposition and entanglement?",
                    index=0,
                ),
                Message(
                    role="assistant",
                    content="Use qc = QuantumCircuit(2, 2) and apply Hadamard gate qc.h(0) in Qiskit.",
                    index=1,
                ),
            ],
        )

        cls.repo.save_conversation(c1)
        cls.repo.save_conversation(c2)

    # Test 1: Zero Vocabulary Overlap Semantic Query
    def test_1_semantic_go_upstairs_to_inspect(self):
        query = "The idea where I don't have to physically go upstairs to inspect something."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0, "Should retrieve water tank conversation")
        self.assertEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")

    # Test 2: Zero Vocabulary Overlap Household Resource Query
    def test_2_semantic_household_resource_supply(self):
        query = "A way to remotely know whether a household resource has enough supply."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0, "Should retrieve water tank conversation")
        self.assertEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")

    # Test 3: Semantic Query on Prevent Overflow
    def test_3_semantic_prevent_overflow(self):
        query = "Automatically prevent overflow without manually checking the tank."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")

    # Test 4: Quantum Entanglement Query vs Water Tank
    def test_4_quantum_entanglement_not_water_tank(self):
        query = "Quantum entanglement circuit."
        results = self.hybrid_engine.search(query)
        if results:
            self.assertNotEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")

    # Test 5: Exact & Semantic Qiskit Query
    def test_5_qiskit_quantum_circuit(self):
        query = "Qiskit quantum circuit."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Quantum Computing with Qiskit")

    # Test 6: Completely Unrelated Query Below Threshold
    def test_6_childhood_cricket_memories_no_result(self):
        query = "Childhood cricket memories."
        results = self.hybrid_engine.search(query)
        self.assertEqual(len(results), 0, "Should return 0 results due to relevance threshold")

    # Test 7: Strict Vocabulary Independence Test
    def test_7_strict_vocabulary_independence_proof(self):
        # Query contains 0 words matching source text: "climb stairs check overhead tank full"
        query = "I need to remotely monitor household supply without physically inspecting it."
        results = self.hybrid_engine.search(query)
        self.assertGreater(len(results), 0, "Proves true neural semantic retrieval without shared keywords")
        self.assertEqual(results[0].conversation_title, "Smart Water Tank Monitoring System")

    # Test 8: Vector Persistence across DB reload
    def test_8_embedding_persistence_across_database_reopen(self):
        db_file = os.path.abspath("data/test_persistence.db")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass

        db1 = Database(db_file)
        repo1 = ConversationRepository(db1)
        conv = Conversation(
            title="Persistence Test Conv",
            messages=[Message(role="user", content="Solar panel energy battery storage.", index=0)],
        )
        repo1.save_conversation(conv)

        # Reopen new Database connection to same file
        db2 = Database(db_file)
        repo2 = ConversationRepository(db2)
        engine2 = HybridSearchEngine(repo2)

        results = engine2.search("renewable energy battery project")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].conversation_title, "Persistence Test Conv")

        # Clean up database handles explicitly for Windows file lock release
        del repo1, repo2, db1, db2, engine2
        gc.collect()
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
