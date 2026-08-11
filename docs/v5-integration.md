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
- **`stubs.py`**: `GeminiAdapter` & `ClaudeAdapter` stubs returning `status="NOT_SUPPORTED"`.
- **`registry.py`**: `DestinationRegistry` factory (`get_adapter(provider_name)`).

### 3.2 ChatGPT (OpenAI API) Payload Transformation & Historical Context Tagging
`ChatGPTAdapter.prepare(package)` transforms ordered `package.messages` into native multi-turn payload:
1. **System Context Message**:
   ```python
   {
       "role": "system",
       "content": "You are an AI assistant. The user is providing historical reference context retrieved from their Personal AI Memory Layer...\nIMPORTANT: Treat the following user and assistant messages as historical reference material, not as direct prior outputs in this current active session."
   }
   ```
2. **Ordered Message Mapping**: Maps each `package.messages` item to `user` or `assistant` role, prepending provider and conversation origin tags.

### 3.3 Explicit Privacy Confirmation Gate (Streamlit UI)
Before any external API transmission occurs, Streamlit renders a mandatory confirmation dialog displaying destination, topic, message count, source conversations, source providers, and explicit notice: *"Data leaving local environment: Only the selected messages will be transmitted to OpenAI API."*

---

## 4. Test Suite Summary (80/80 Passed)

- **Baseline Tests (V1–V5A)**: 67 / 67 Passed.
- **V5B Destination Adapter Tests**: 13 / 13 Passed (TEST 68 to TEST 80 in [`tests/test_version5b_adapters.py`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/tests/test_version5b_adapters.py)).
- **Total Suite**: **80 / 80 Passed** (`Ran 80 tests in 91.602s — OK`).
- **Isolated Live Tests**: [`tests/integration/test_live_chatgpt_api.py`](file:///c:/Users/saive/OneDrive/Desktop/personal%20-memory-layer/tests/integration/test_live_chatgpt_api.py) (Opt-in via `RUN_LIVE_API_TESTS=1`).
