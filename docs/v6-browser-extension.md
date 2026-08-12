# Milestone V6 — Universal AI Memory Browser Extension Architecture

## Overview

The Personal AI Memory Layer Browser Extension (Manifest V3) turns the Memory Layer engine into an in-browser interface accessible directly inside supported AI chat websites (ChatGPT, Gemini, Claude).

The extension acts strictly as the **user-facing product layer**, communicating with the local Memory Layer backend over a localhost REST API (`http://127.0.0.1:8000/api/v1`).

---

## Support Status Matrix

| Component / Feature | Support Status | Notes |
| :--- | :--- | :--- |
| **Local REST API Backend (`app/api/server.py`)** | **IMPLEMENTED** | Zero-dependency Python server on port 8000. |
| **Manifest V3 Extension Skeleton** | **IMPLEMENTED** | Located in `extension/`. |
| **Activation Gate (`chrome.storage.local`)** | **IMPLEMENTED** | Explicit user permission toggle ("Enable Memory Layer on AI sites"). |
| **ChatGPT Adapter (`ChatGPTAdapter`)** | **IMPLEMENTED (Target V6.1)** | Active implementation for `chatgpt.com` / `chat.openai.com`. |
| **Search This Conversation (DOM vs History)** | **IMPLEMENTED** | Distinguishes webpage DOM messages vs backend history. |
| **Search All AI Memory (Global Search)** | **IMPLEMENTED** | Searches complete indexed SQLite database. |
| **Prompt Composer Insertion (INSERT ONLY)** | **IMPLEMENTED** | Inserts context into prompt box; NEVER auto-sends. |
| **Gemini Adapter (`GeminiAdapter`)** | **PLANNED / STUB** | Structured adapter stub (V6.6 planned). |
| **Claude Adapter (`ClaudeAdapter`)** | **PLANNED / STUB** | Structured adapter stub (V6.7 planned). |

---

## Security Decisions & Local Boundaries

1. **Restricted CORS Policy**:
   - The backend server does **NOT** use `Access-Control-Allow-Origin: *`.
   - Origin checking enforces `chrome-extension://...` and local development origins (`http://localhost`, `http://127.0.0.1`).
2. **Restricted API Boundary**:
   - SQLite database (`data/memory.db`) and vector embedding logic are **never** directly exposed to the extension.
   - Only explicitly defined JSON REST endpoints (`/api/v1/*`) are served.
3. **No Automatic Message Sending**:
   - Context insertion performs `INSERT ONLY`. The extension never clicks Send or submits prompts automatically.

---

## Local REST API Endpoints (`http://127.0.0.1:8000`)

- `GET /api/v1/health`: Connection status and version check.
- `GET /api/v1/conversations`: List stored conversations.
- `GET /api/v1/conversations/{id}`: Detailed conversation view with messages.
- `POST /api/v1/search`: Global hybrid search across memory history.
- `POST /api/v1/search/conversation`: In-conversation ephemeral search.
- `POST /api/v1/context/compose`: Multi-topic composition (`PortableContextPackage`).
- `POST /api/v1/context/handoff`: Handoff context to live destination adapters.
