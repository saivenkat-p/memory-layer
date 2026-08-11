# Milestone V5 — Live AI Integration Architecture (V5A Foundation & V5B Destination Adapters)

## 1. Executive Summary & Core Architectural Principle

Milestone V5 establishes the architectural boundary between the **Personal AI Memory Layer** and **External AI Platforms**:

```text
┌─────────────────────────────────────────────────────────────┐
│                 PERSONAL AI MEMORY LAYER                    │
│                                                             │
│ 🧠 REMEMBER      🔍 FIND HERE      🌿 CONTINUE    🧩 COMPOSE │
│                                                             │
│                      [V4 ComposedContext]                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                V5A — PORTABLE CONTEXT PACKAGE               │
│                                                             │
│  schema_version: "1.0"                                      │
│  deterministic_text_formatting                              │
│  provenance_audit_records                                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               V5B — DESTINATION ADAPTER LAYER               │
│                                                             │
│ ┌──────────────────┬──────────────────┬──────────────────┐  │
│ │  Local Export    │  ChatGPT (API)   │  Gemini / Claude │  │
│ │  Adapter         │  Adapter         │  Stubs           │  │
│ └─────────┬────────┴─────────┬────────┴─────────┬────────┘  │
│           ▼                  ▼                  ▼           │
│     Offline JSON       OpenAI Chat API   Planned (Future)   │
└─────────────────────────────────────────────────────────────┘
```

### Architectural Ownership Separation
- **V4 owns**: `retrieval`, `selection`, `composition`, `provenance`, `ordering`.
- **V5A owns**: `PortableContextPackage (v1.0)` creation, schema validation, deterministic text rendering.
- **V5B owns**: `DestinationAdapter` interface, `DestinationResult` schema, `ChatGPT (OpenAI API)` adapter, privacy confirmation gate.

---

## 2. V5A Foundation — Portable Context Package & Export Engine

### 2.1 Provider-Independent Versioned Schema (`schema_version: "1.0"`)
The `PortableContextPackage` dataclass ([`app/models/schemas.py`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/app/models/schemas.py)) defines a strict, versioned contract:

```json
{
  "schema_version": "1.0",
  "package_id": "8f3b2a1c-9d0e-4f5a-8b7c-6d5e4f3a2b1c",
  "title": "Composed: Funding & Multi-AI Strategy",
  "topic": "Funding strategy and cross-AI integration",
  "created_at": "2026-08-11T15:00:00Z",
  "total_messages": 12,
  "source_conversations": [
    { "id": "conv-101", "title": "Startup Pitch", "source": "ChatGPT" },
    { "id": "conv-102", "title": "Memory Layer Architecture", "source": "Gemini" }
  ],
  "source_providers": {
    "ChatGPT": 8,
    "Gemini": 4
  },
  "context_text": "# Context from Personal AI Memory Layer...",
  "messages": [
    {
      "order": 1,
      "message_id": "msg-001",
      "conversation_id": "conv-101",
      "conversation_title": "Startup Pitch",
      "provider": "ChatGPT",
      "role": "user",
      "content": "How do we pitch angel investors?",
      "message_index": 0,
      "timestamp": "2026-08-10T12:00:00Z"
    }
  ],
  "provenance": [
    {
      "order": 1,
      "message_id": "msg-001",
      "source_conversation_id": "conv-101",
      "source_provider": "ChatGPT",
      "original_index": 0
    }
  ]
}
```

---

## 3. V5B Live AI Integration Architecture

### 3.1 Destination Adapters Package (`app/services/destination_adapters/`)
- **`base.py`**: Defines `DestinationResult` schema and `DestinationAdapter` ABC (`provider_name`, `is_supported`, `validate()`, `prepare()`, `execute()`).
- **`local.py`**: `LocalExportAdapter` wrapping offline package generation.
- **`chatgpt.py`**: `ChatGPTAdapter` transforming `PortableContextPackage` into native multi-turn messages array for official OpenAI Chat API.
- **`gemini.py`**: `GeminiAdapter` transforming `PortableContextPackage` into native multi-turn contents array for official Google Gemini API (`gemini-1.5-flash`).
- **`stubs.py`**: `ClaudeAdapter` stub returning `status="NOT_SUPPORTED"`.
- **`registry.py`**: `DestinationRegistry` factory (`get_adapter(provider_name)`).

### 3.2 Provider Payload Transformations & Historical Context Tagging
- **`ChatGPTAdapter.prepare(package)`**: Transforms `package.messages` into `messages` array (`role: "user"` / `role: "assistant"`) with `system` instruction.
- **`GeminiAdapter.prepare(package)`**: Transforms `package.messages` into `contents` array (`role: "user"` / `role: "model"`) with `system_instruction`.

### 3.3 Explicit Privacy Confirmation Gate (Streamlit UI)
Before any external API transmission occurs, Streamlit renders a mandatory confirmation dialog displaying destination, topic, message count, source conversations, source providers, and explicit notice of data leaving local machine.

---

## 4. Test Suite Summary (81/81 Passed)

- **Baseline Tests (V1–V5A)**: 67 / 67 Passed.
- **V5B Destination Adapter Tests**: 14 / 14 Passed (TEST 68 to TEST 81 in [`tests/test_version5b_adapters.py`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/tests/test_version5b_adapters.py)).
- **Total Suite**: **81 / 81 Passed** (`Ran 81 tests in 239.509s — OK`).
- **Isolated Live Tests**: [`tests/integration/test_live_chatgpt_api.py`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/tests/integration/test_live_chatgpt_api.py) (Opt-in via `RUN_LIVE_API_TESTS=1`).
