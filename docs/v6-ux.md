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
