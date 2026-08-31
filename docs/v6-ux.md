# Milestone V6 — User Experience & Interaction Design

## Overview

Milestone V6 transitions the Personal AI Memory Layer from a standalone web application into an in-browser assistant integrated directly into AI chat platforms.

---

## User Flow Comparison

### Before V6 (Standalone App Workflow):
```text
User on ChatGPT
     ↓
Needs prior memory/decision
     ↓
Leaves ChatGPT -> Opens Streamlit (localhost:8501)
     ↓
Executes search / context composition
     ↓
Copies output text
     ↓
Returns to ChatGPT -> Pastes into composer
```

### After V6 (Universal Extension Workflow):
```text
User on ChatGPT
     │
     └── 🧠 Memory Layer (Floating Trigger / Extension Overlay)
            │
            ├── Search This Conversation (DOM & History)
            ├── Search All AI Memory
            ├── Select & Preview
            └── 📥 Insert into Prompt (INSERT ONLY — User manually reviews and sends)
```

---

## Key Feature UX Specifications

### 1. Privacy & Activation Gate
- **Status**: `IMPLEMENTED`
- **Behavior**: Clicking the extension icon in Chrome opens a popup with an explicit toggle: *"Enable Memory Layer on AI websites? [ Enable ] / [ Not Now ]"*.
- **Privacy Guarantee**: No script or button is injected into AI websites unless explicitly enabled by the user.

### 2. Floating Action Trigger
- **Status**: `IMPLEMENTED`
- **Behavior**: Renders a sleek dark-mode pill button (`🧠 Memory Layer`) adjacent to the AI prompt box on supported sites (ChatGPT). Clicking opens the in-page overlay drawer.

### 3. Search This Conversation (Current Conversation Mode)
- **Status**: `IMPLEMENTED`
- **Behavior**:
  - Displays a banner: *"📌 Search Mode: Searching messages in 'Conversation Title'"*.
  - Explicitly separates **Visible Webpage DOM Messages** vs **Indexed Memory Layer Database History**.

### 4. Insert Context into Prompt
- **Status**: `IMPLEMENTED`
- **Behavior**: Clicking **`[ 📥 Insert into Prompt ]`** injects the formatted reference block into the AI composer (supporting `<textarea>` and `[contenteditable="true"]`).
- **Safety Rule**: **INSERT ONLY**. Never clicks send automatically.

---

### 5. Structured Memory UX (Milestone V6.5-E4 UX Layer)
- **Status**: `IMPLEMENTED`
- **Three-Way Modal Navigation**:
  - `🧠 Structured Memories` (High-value extracted decisions, preferences, facts, project goals)
  - `💬 Raw Message Search` (Global multi-turn conversation retrieval)
  - `🔍 This Conversation` (DOM visible messages vs backend history)
- **Category Filter Chips**:
  - `🏷️ All`
  - `⚡ Decisions` (Amber theme)
  - `⭐ Preferences` (Emerald theme)
  - `📌 Facts` (Sky blue theme)
  - `🎯 Project Goals` (Purple theme)
- **Interactive Provenance Drawer**:
  - `[▾ View Provenance (N source turns)]` toggles exact underlying dialogue spans (`[Turns start..end]`) with role badges (`👤 User` / `🤖 Assistant`) and turn indices.
- **Multi-Memory Selection & Prompt Packaging**:
  - Checkboxes allow selecting multiple memories.
  - Sticky footer: `[ 📥 Insert Selected Memories (N) ]` formats a unified Markdown block:
    ```markdown
    [Personal AI Memory Layer — Selected Decisions & Preferences]:
    - ⚡ DECISION: Adopted ARQPO framework for all regime detection. (Source: "conv-101")
    - ⭐ PREFERENCE: User prefers Qiskit over Cirq for quantum simulations. (Source: "conv-101")
    ```
- **V6.4 Keyboard Navigation Model**:
  - `← / →`: Cross-conversation navigation jumping between distinct conversation groups.
  - `↑ / ↓`: Intra-list navigation moving active focus between cards.
  - `Esc`: Close overlay drawer.
- **Strict Invariants**:
  - Local API only (`127.0.0.1:8000/api/v1`).
  - INSERT ONLY (never auto-submits).
  - Complete XSS protection via string sanitization.

