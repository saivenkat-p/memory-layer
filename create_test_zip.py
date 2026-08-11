"""
Generates data/test_bulk_history.zip containing 3 realistic ChatGPT conversations.
"""

import os
import json
import zipfile

def create_bulk_zip():
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    zip_path = os.path.join(data_dir, "test_bulk_history.zip")

    conv1 = {
        "title": "Personal AI Memory Layer Project",
        "source": "ChatGPT",
        "created_at": "2026-08-10T10:00:00Z",
        "messages": [
            {
                "role": "user",
                "content": "I want to create a system where I can search across all my old AI conversations without needing to remember where I discussed something.",
                "timestamp": "2026-08-10T10:00:01Z"
            },
            {
                "role": "assistant",
                "content": "That is the core philosophy of a Personal AI Memory Layer. By pairing keyword search with local neural vector embeddings, you can describe memories in your own words.",
                "timestamp": "2026-08-10T10:00:05Z"
            },
            {
                "role": "user",
                "content": "What local embedding model should we use?",
                "timestamp": "2026-08-10T10:01:00Z"
            },
            {
                "role": "assistant",
                "content": "You can use sentence-transformers with the all-MiniLM-L6-v2 model, which produces 384-dimensional dense vectors running locally on CPU.",
                "timestamp": "2026-08-10T10:01:05Z"
            }
        ]
    }

    conv2 = {
        "title": "Quantum Computing with Qiskit",
        "source": "ChatGPT",
        "created_at": "2026-08-10T11:00:00Z",
        "messages": [
            {
                "role": "user",
                "content": "How do I build a quantum circuit using Qiskit in Python?",
                "timestamp": "2026-08-10T11:00:01Z"
            },
            {
                "role": "assistant",
                "content": "In Qiskit, you initialize a QuantumCircuit(2, 2), apply Hadamard gates for superposition and CNOT gates for quantum entanglement, then measure qubits.",
                "timestamp": "2026-08-10T11:00:08Z"
            },
            {
                "role": "user",
                "content": "Can we simulate a Bell state measurement?",
                "timestamp": "2026-08-10T11:02:00Z"
            },
            {
                "role": "assistant",
                "content": "Yes, use AerSimulator from qiskit_aer to execute the circuit and plot a histogram of the entangled measurement outcomes.",
                "timestamp": "2026-08-10T11:02:06Z"
            }
        ]
    }

    conv3 = {
        "title": "Smart Water Tank IoT Monitoring Idea",
        "source": "ChatGPT",
        "created_at": "2026-08-10T12:00:00Z",
        "messages": [
            {
                "role": "user",
                "content": "I don't want to climb the stairs to check whether the overhead water tank is full. I want a system that shows the water level remotely and automatically stops the motor.",
                "timestamp": "2026-08-10T12:00:01Z"
            },
            {
                "role": "assistant",
                "content": "You can build a smart water tank monitoring system using an ultrasonic sensor (HC-SR04) mounted on top of the tank paired with an ESP32 micro-controller and a relay module.",
                "timestamp": "2026-08-10T12:00:10Z"
            },
            {
                "role": "user",
                "content": "How will it prevent overflow automatically?",
                "timestamp": "2026-08-10T12:01:00Z"
            },
            {
                "role": "assistant",
                "content": "When the distance measured by the ultrasonic sensor indicates the water level reached 95% capacity, the ESP32 triggers the relay to automatically cut power to the water pump motor.",
                "timestamp": "2026-08-10T12:01:07Z"
            }
        ]
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("conversation_1.json", json.dumps(conv1, indent=2))
        zf.writestr("conversation_2.json", json.dumps(conv2, indent=2))
        zf.writestr("conversation_3.json", json.dumps(conv3, indent=2))

    print(f"Created ZIP archive at: {zip_path}")
    print(f"Archive contents: {zipfile.ZipFile(zip_path).namelist()}")

if __name__ == "__main__":
    create_bulk_zip()
