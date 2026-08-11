"""
Personal AI Memory Layer - Streamlit Web Application MVP with Neural Hybrid Search & Debug Mode.

Main entry point integrating Conversation Parsing, Database Storage,
Neural Hybrid Search Engine (SentenceTransformers), Source Context Viewer, and Ask My Memory Assistant.
"""

import os
import sys

# Suppress progress bars and HF warnings before importing sentence-transformers
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Fix Windows Streamlit sys.stderr.flush OSError [Errno 22] bug during tqdm output
class SafeStreamWrapper:
    def __init__(self, original_stream):
        self._original = original_stream

    def write(self, s):
        try:
            return self._original.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            if hasattr(self._original, "flush"):
                return self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)

if sys.stderr is not None and not getattr(sys.stderr, "_is_safe_wrapper", False):
    sys.stderr = SafeStreamWrapper(sys.stderr)
    sys.stderr._is_safe_wrapper = True

if sys.stdout is not None and not getattr(sys.stdout, "_is_safe_wrapper", False):
    sys.stdout = SafeStreamWrapper(sys.stdout)
    sys.stdout._is_safe_wrapper = True

import streamlit as st
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.parsers.factory import parse_conversation_file
from app.parsers.base import ParsingError
from app.search.hybrid_search import HybridSearchEngine
from app.ai.memory_assistant import AskMyMemoryAssistant

# Enable development debug mode to inspect scores in UI
DEBUG_SEMANTIC_SEARCH = True

# Configure Streamlit page layout and theme
st.set_page_config(
    page_title="Personal AI Memory Layer",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished UX
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4F46E5, #9333EA);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #9CA3AF;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .chat-user {
        background: rgba(59, 130, 246, 0.15);
        border-left: 4px solid #3B82F6;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 8px;
    }
    .chat-assistant {
        background: rgba(147, 51, 234, 0.15);
        border-left: 4px solid #9333EA;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 8px;
    }
    .context-highlight {
        background: rgba(234, 179, 8, 0.2);
        border: 1px solid #EAB308;
        padding: 12px;
        border-radius: 8px;
    }
    .score-badge {
        background-color: rgba(79, 70, 229, 0.3);
        color: #818CF8;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .debug-box {
        background: rgba(30, 41, 59, 0.5);
        border: 1px dashed #64748B;
        padding: 8px 12px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.85rem;
        margin-top: 6px;
    }
</style>
""", unsafe_allow_html=True)
from app.services.bulk_import import BulkImportEngine
from app.search.find_here import FindHereEngine
from app.services.topic_extractor import TopicExtractionEngine
from app.services.context_composer import ContextComposer
from app.services.export_engine import LocalExportDestination
from app.services.destination_adapters.registry import DestinationRegistry


@st.cache_resource
def get_services():
    """Initializes singletons for Database, Repository, HybridSearchEngine, Assistant, BulkImportEngine, FindHereEngine, TopicExtractionEngine, ContextComposer, LocalExportDestination, and DestinationRegistry."""
    db_path = os.path.join("data", "memory.db")
    db = Database(db_path)
    repo = ConversationRepository(db)
    search_engine = HybridSearchEngine(repo)
    assistant = AskMyMemoryAssistant(search_engine)
    bulk_engine = BulkImportEngine(repo)
    find_here_engine = FindHereEngine(repo)
    topic_extractor = TopicExtractionEngine(repo)
    composer = ContextComposer(repo, search_engine)
    local_exporter = LocalExportDestination()
    dest_registry = DestinationRegistry()
    return repo, search_engine, assistant, bulk_engine, find_here_engine, topic_extractor, composer, local_exporter, dest_registry


try:
    repo, search_engine, assistant, bulk_engine, find_here_engine, topic_extractor, composer, local_exporter, dest_registry = get_services()
    if not hasattr(search_engine.semantic_engine.encoder, "model") or search_engine.semantic_engine.encoder.model is None:
        st.cache_resource.clear()
        repo, search_engine, assistant, bulk_engine, find_here_engine, topic_extractor, composer, local_exporter, dest_registry = get_services()
except Exception:
    st.cache_resource.clear()
    repo, search_engine, assistant, bulk_engine, find_here_engine, topic_extractor, composer, local_exporter, dest_registry = get_services()


# Sidebar Navigation
st.sidebar.title("🧠 Memory Layer")
st.sidebar.markdown("*Don't remember WHERE. Search WHAT you discussed.*")
st.sidebar.divider()

nav_option = st.sidebar.radio(
    "Navigation",
    options=[
        "📊 Dashboard",
        "📥 Import History",
        "💬 Conversations",
        "🧩 Compose Context",
        "🔍 Search Memory",
        "🤖 Ask My Memory",
        "🏷️ Categories & Tags",
        "⚙️ Data & Settings",
    ],
)


# Helper function to seed sample data with deduplication
def seed_demo_data():
    sample_files = [
        ("data/sample_chatgpt.json", "sample_chatgpt.json"),
        ("data/sample_chat.txt", "sample_chat.txt"),
    ]
    added = 0
    existing_titles = [c.title for c in repo.list_conversations()]

    for path, name in sample_files:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                conv = parse_conversation_file(content, name)
                if conv.title not in existing_titles:
                    if name.endswith("json"):
                        conv.category = "Startup Idea"
                        conv.tags = ["IoT", "Water", "Automation"]
                        conv.description = "Smart water tank monitoring project"
                    else:
                        conv.category = "Learning"
                        conv.tags = ["Quantum", "Python", "Physics"]
                        conv.description = "Qiskit quantum circuit notes"
                    repo.save_conversation(conv)
                    added += 1
            except Exception:
                pass
    return added


# -----------------------------------------------------------------------------
# VIEW 1: DASHBOARD
# -----------------------------------------------------------------------------
if nav_option == "📊 Dashboard":
    st.markdown('<div class="main-header">Personal AI Memory Layer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Your searchable personal knowledge base across AI conversations.</div>', unsafe_allow_html=True)

    stats = repo.get_stats()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Conversations", stats["total_conversations"])
    with c2:
        st.metric("Total Messages Stored", stats["total_messages"])
    with c3:
        st.metric("AI Sources Connected", len(stats["sources"]))

    st.divider()

    if stats["total_conversations"] == 0:
        st.info("👋 Welcome! Your memory layer is currently empty.")
        if st.button("🚀 Load Sample Conversations (Demo Data)", type="primary"):
            added = seed_demo_data()
            st.success(f"Successfully loaded sample conversations! Refreshing...")
            st.rerun()
    else:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.subheader("🕒 Recently Imported Conversations")
            recent_convs = repo.list_conversations(limit=5)
            for conv in recent_convs:
                with st.expander(f"💬 {conv.title} ({conv.source}) — {conv.message_count} msgs"):
                    st.caption(f"Imported: {conv.imported_at[:10]} | Category: {conv.category or 'Uncategorized'} | Tags: {', '.join(conv.tags)}")
                    if conv.description:
                        st.write(f"*{conv.description}*")
                    for msg in conv.messages[:3]:
                        role_icon = "👤" if msg.role == "user" else "🤖"
                        st.markdown(f"**{role_icon} {msg.role.title()}:** {msg.content[:120]}...")

        with col_right:
            st.subheader("📊 Source Breakdown")
            if stats["sources"]:
                for src, count in stats["sources"].items():
                    st.write(f"• **{src}**: {count} conversation(s)")


# -----------------------------------------------------------------------------
# VIEW 2: IMPORT HISTORY (BULK & SINGLE)
# -----------------------------------------------------------------------------
elif nav_option == "📥 Import History":
    st.markdown('<div class="main-header">Import History</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Import your complete AI conversation history (ChatGPT export ZIP/JSON, Gemini, Claude, or TXT logs).</div>', unsafe_allow_html=True)

    import_mode = st.radio(
        "Import Mode",
        ["📦 Bulk History Import (Recommended)", "📄 Single Conversation File"],
        horizontal=True,
    )

    if import_mode == "📦 Bulk History Import (Recommended)":
        st.info("💡 **Upload your exported conversation history archive (`.zip`) or bulk export file (`conversations.json`).** The system will parse all conversations, skip duplicates, and generate neural vector embeddings automatically.")

        uploaded_archive = st.file_uploader(
            "Select exported archive or bulk file",
            type=["zip", "json", "txt"],
            key="bulk_uploader",
        )

        skip_duplicates = st.checkbox("Skip duplicate conversations during import", value=True)

        if uploaded_archive is not None:
            file_bytes = uploaded_archive.read()
            file_name = uploaded_archive.name

            if st.button("🚀 Start Bulk Import & Neural Indexing", type="primary"):
                progress_bar = st.progress(0.0)
                status_text = st.empty()

                def streamlit_progress_cb(current: int, total: int, message: str):
                    pct = float(current) / float(total) if total > 0 else 0.0
                    progress_bar.progress(min(1.0, max(0.0, pct)))
                    status_text.markdown(f"⏳ **{message}**")

                with st.spinner("Processing bulk export data..."):
                    result = bulk_engine.import_archive_or_file(
                        file_bytes,
                        file_name,
                        progress_callback=streamlit_progress_cb,
                        skip_duplicates=skip_duplicates,
                    )

                status_text.empty()
                progress_bar.empty()

                st.success("🎉 **Bulk History Import Complete!**")

                st.subheader("📊 Import Summary Report")
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric("Conversations Detected", result.conversations_detected)
                with col_m2:
                    st.metric("Conversations Imported", result.conversations_imported)
                with col_m3:
                    st.metric("Duplicates Skipped", result.duplicates_skipped)
                with col_m4:
                    st.metric("Messages Ingested", result.messages_imported)

                if result.skipped_items:
                    with st.expander("ℹ️ Details on Skipped / Failed Items"):
                        for item in result.skipped_items:
                            st.write(f"• {item}")

                st.toast(f"Imported {result.conversations_imported} conversation(s) successfully!", icon="✅")

    else:
        # Single File Import Mode
        uploaded_file = st.file_uploader("Select single conversation file", type=["json", "txt", "md"], key="single_uploader")

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            file_name = uploaded_file.name

            try:
                parsed_conv = parse_conversation_file(file_bytes, file_name)
                st.success(f"✅ Successfully parsed '{parsed_conv.title}' ({parsed_conv.message_count} messages extracted)")

                st.subheader("Manual Metadata (Optional)")
                col_a, col_b = st.columns(2)
                with col_a:
                    category = st.selectbox(
                        "Category",
                        ["Startup Idea", "Learning", "Research", "Project", "Personal", "Other"],
                        index=0,
                    )
                    tags_input = st.text_input("Tags (comma separated)", value="AI, Notes")
                with col_b:
                    description = st.text_area("Description / Summary", value=f"Imported conversation from {parsed_conv.source}")

                parsed_conv.category = category
                parsed_conv.tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                parsed_conv.description = description

                with st.expander("👀 Preview Parsed Messages", expanded=False):
                    for msg in parsed_conv.messages:
                        role_class = "chat-user" if msg.role == "user" else "chat-assistant"
                        st.markdown(f'<div class="{role_class}"><b>{msg.role.title()}:</b> {msg.content}</div>', unsafe_allow_html=True)

                if st.button("💾 Save Conversation to Memory Layer", type="primary"):
                    repo.save_conversation(parsed_conv)
                    st.toast("Conversation saved successfully with neural vector embeddings!", icon="🎉")
                    st.success("Saved! You can now search for topics discussed in this conversation.")

            except ParsingError as e:
                st.error(f"❌ Failed to parse file: {e}")


# -----------------------------------------------------------------------------
# VIEW 3: CONVERSATIONS LIST (WITH FIND HERE & CONTINUE TOPIC)
# -----------------------------------------------------------------------------
elif nav_option == "💬 Conversations":
    st.markdown('<div class="main-header">Stored Conversations</div>', unsafe_allow_html=True)

    convs = repo.list_conversations(limit=100)

    if not convs:
        st.info("No conversations stored yet. Use the 'Import History' tab or load sample data from Dashboard.")
    else:
        st.write(f"Showing {len(convs)} conversation(s):")

        for conv in convs:
            with st.expander(f"💬 {conv.title} | Source: {conv.source} | Messages: {conv.message_count}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**Imported:** {conv.imported_at[:19]}")
                    st.write(f"**Category:** {conv.category or 'None'} | **Tags:** {', '.join(conv.tags) if conv.tags else 'None'}")
                    if conv.description:
                        st.write(f"**Description:** {conv.description}")
                    
                    # Display Parent / Child Continuation Relationships (Version 3)
                    rel_data = repo.get_relationships(conv.id)
                    if rel_data["parent"]:
                        p = rel_data["parent"]
                        st.info(f"🌿 **Derived Continuation**: Extracted from **'{p['parent_title']}'** on topic: *'{p['topic']}'*")
                    if rel_data["children"]:
                        for ch in rel_data["children"]:
                            st.caption(f"🌿 **Derived Topic Chat**: '{ch['child_title']}' (Topic: '{ch['topic']}')")

                with c2:
                    if st.button("🗑️ Delete", key=f"del_{conv.id}", type="secondary"):
                        repo.delete_conversation(conv.id)
                        st.rerun()

                st.divider()

                # Feature 1: 🔍 FIND HERE (In-Conversation Temporary Search)
                with st.expander("🔍 Find in this conversation", expanded=False):
                    find_query = st.text_input(
                        "What are you looking for inside this conversation?",
                        key=f"find_input_{conv.id}",
                        placeholder="e.g. where did we discuss Version 2?",
                    )
                    if find_query:
                        find_results = find_here_engine.search_in_conversation(conv.id, find_query)
                        if not find_results:
                            st.warning(f"No matches found for '{find_query}' inside this conversation.")
                        else:
                            st.success(f"Found {len(find_results)} match(es) in this conversation:")
                            for m_idx, match in enumerate(find_results, start=1):
                                st.markdown(
                                    f"**Match #{m_idx}** | Message #{match.msg_index} ({match.matched_role.title()}) — Score: **{match.score}%**"
                                )
                                st.markdown(f'<div class="debug-box">"{match.snippet}"</div>', unsafe_allow_html=True)
                                if st.button(f"📍 Jump to Match #{m_idx}", key=f"jump_{conv.id}_{match.message_id}"):
                                    st.session_state[f"jump_msg_{conv.id}"] = match.msg_index

                # Display Jump Context Window if user clicked Jump to Match
                jump_target = st.session_state.get(f"jump_msg_{conv.id}")
                if jump_target is not None:
                    st.info(f"📍 **Focusing Message #{jump_target} Window:**")
                    ctx = search_engine.keyword_engine.get_source_context(conv.id, jump_target, window=2)
                    for msg in ctx["window_messages"]:
                        is_target = (msg.index == jump_target)
                        style = "border: 2px solid #3B82F6; background: rgba(59,130,246,0.15);" if is_target else ""
                        role_class = "chat-user" if msg.role == "user" else "chat-assistant"
                        st.markdown(f'<div class="{role_class}" style="{style}"><b>Msg #{msg.index} {msg.role.title()}:</b> {msg.content}</div>', unsafe_allow_html=True)

                st.divider()

                # Feature 2: 🌿 CONTINUE TOPIC (Context Extraction & Isolation)
                with st.expander("🌿 Continue Topic into a Focused Chat", expanded=False):
                    topic_input = st.text_input(
                        "What topic do you want to extract and continue?",
                        key=f"topic_input_{conv.id}",
                        placeholder="e.g. Personal AI Memory Layer",
                    )
                    if st.button("🔍 Find Relevant Context", key=f"find_ctx_btn_{conv.id}"):
                        if topic_input:
                            preview = topic_extractor.extract_topic_context(conv.id, topic_input)
                            st.session_state[f"preview_{conv.id}"] = preview

                    preview = st.session_state.get(f"preview_{conv.id}")
                    if preview and preview.parent_conversation_id == conv.id:
                        st.subheader(f"🌿 Topic Preview: '{preview.topic}'")
                        st.write(f"✓ Found **{preview.total_context_messages} relevant message(s)** ({preview.direct_match_count} direct matches).")
                        
                        selected_msg_ids = []
                        for sel_msg in preview.selected_messages:
                            label = f"Msg #{sel_msg.original_index} ({sel_msg.role.title()}): {sel_msg.content[:100]}..."
                            check_val = st.checkbox(label, value=True, key=f"cb_{conv.id}_{sel_msg.message_id}")
                            if check_val:
                                selected_msg_ids.append(sel_msg.message_id)

                        if st.button("🌿 Create Focused Continuation Chat", key=f"create_chat_{conv.id}", type="primary"):
                            if selected_msg_ids:
                                new_chat = topic_extractor.create_continued_conversation(
                                    parent_conversation_id=conv.id,
                                    topic=preview.topic,
                                    selected_message_ids=selected_msg_ids,
                                )
                                st.toast(f"Created focused chat '{new_chat.title}'!", icon="🎉")
                                st.success(f"Created derived conversation **'{new_chat.title}'** with {new_chat.message_count} messages!")
                                del st.session_state[f"preview_{conv.id}"]
                                st.rerun()

                st.divider()
                st.markdown("### Full Conversation History")
                for msg in conv.messages:
                    role_class = "chat-user" if msg.role == "user" else "chat-assistant"
                    st.markdown(f'<div class="{role_class}"><b>Msg #{msg.index} {msg.role.title()}:</b> {msg.content}</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# VIEW 4: COMPOSE CONTEXT (MULTI-TOPIC / MULTI-CONVERSATION CONTEXT COMPOSITION)
# -----------------------------------------------------------------------------
elif nav_option == "🧩 Compose Context":
    st.markdown('<div class="main-header">🧩 Compose Context</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Discover, select, reorder, and combine relevant context blocks from multiple conversations across AI platforms into a new focused chat.</div>',
        unsafe_allow_html=True,
    )

    st.info("💡 **Enter what you want to bring together.** The engine will search your complete indexed history across all AI providers, allowing you to select and reorder the exact context blocks you want.")

    comp_query = st.text_input(
        "Describe what context you want to bring together",
        key="compose_query_input",
        placeholder="e.g. Memory Layer, funding strategy, and using it across ChatGPT/Gemini",
    )

    col_btn1, col_btn2 = st.columns([2, 3])
    with col_btn1:
        if st.button("🔍 Search & Group Relevant Context", type="primary", key="compose_search_btn"):
            if comp_query:
                with st.spinner("Searching multi-topic context across memory..."):
                    grouped_results = composer.search_context(comp_query, limit=50)
                    st.session_state["compose_grouped_results"] = grouped_results
                    st.session_state["compose_query_active"] = comp_query
                    init_selected = []
                    for cid, grp in grouped_results.items():
                        if cid != "_diagnostics" and "candidates" in grp:
                            for cand in grp["candidates"]:
                                init_selected.append(cand)
                    st.session_state["compose_selected_candidates"] = init_selected

    grouped = st.session_state.get("compose_grouped_results", {})
    selected_cands = st.session_state.get("compose_selected_candidates", [])

    if grouped:
        diagnostics = grouped.get("_diagnostics")
        conv_groups = {k: v for k, v in grouped.items() if k != "_diagnostics"}

        st.divider()

        # Multi-Topic Diagnostics Expander
        if diagnostics:
            with st.expander("🔍 View Multi-Topic Diagnostics & Ranking Breakdown", expanded=False):
                st.markdown(f"**Composition Query:** `{diagnostics.get('original_query', diagnostics.get('query'))}`")
                st.markdown(f"**Detected Sub-Topics ({len(diagnostics['detected_topics'])}):** {', '.join(f'`{t}`' for t in diagnostics['detected_topics'])}")
                
                diag_c1, diag_c2, diag_c3, diag_c4 = st.columns(4)
                with diag_c1:
                    st.metric("Raw Candidates Found", diagnostics["total_raw_candidates"])
                with diag_c2:
                    st.metric("Duplicates Removed", diagnostics["duplicates_removed"])
                with diag_c3:
                    st.metric("Conversations Identified", diagnostics["conversations_found"])
                with diag_c4:
                    st.metric("AI Providers", diagnostics["providers_found"])

                st.caption(f"Candidates per topic: {diagnostics['candidates_per_topic']}")

        st.subheader("📊 Step 1: Select Context Candidates")

        tot_cands = sum(len(grp["candidates"]) for grp in conv_groups.values())
        tot_providers = len(set(grp["source"] for grp in conv_groups.values()))

        st.markdown(f"Found **{tot_cands} candidate message(s)** across **{len(conv_groups)} conversation(s)** and **{tot_providers} AI provider(s)**:")

        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            if st.button("☑️ Select All Candidates", key="select_all_btn"):
                all_cands = []
                for grp in conv_groups.values():
                    all_cands.extend(grp["candidates"])
                st.session_state["compose_selected_candidates"] = all_cands
                st.rerun()
        with col_sel2:
            if st.button("☐ Clear Selection", key="clear_all_btn"):
                st.session_state["compose_selected_candidates"] = []
                st.rerun()

        # Render candidates grouped by Conversation
        current_selected_ids = {c.message_id for c in selected_cands}
        new_selected_map = {}

        for cid, grp in conv_groups.items():
            badge = " [V3 Continuation]" if grp.get("is_derived") else " [Original Parent]"
            with st.expander(f"💬 {grp['title']}{badge} | Source: **{grp['source']}** | Max Relevance: **{grp['max_score']}%**", expanded=True):
                for cand in grp["candidates"]:
                    is_checked = cand.message_id in current_selected_ids
                    label = f"Msg #{cand.message_index} ({cand.role.title()}) [Topic: {cand.topic_association} | Raw Sem: {cand.raw_semantic_score} | Score: {cand.relevance_score}%]: {cand.content[:120]}..."
                    val = st.checkbox(label, value=is_checked, key=f"chk_comp_{cand.message_id}")
                    if val:
                        new_selected_map[cand.message_id] = cand

        # Update selected candidates list preserving order
        ordered_selected = [c for c in selected_cands if c.message_id in new_selected_map]
        for mid, cand in new_selected_map.items():
            if not any(c.message_id == mid for c in ordered_selected):
                ordered_selected.append(cand)
        st.session_state["compose_selected_candidates"] = ordered_selected

        # Step 2: Context Preview & Reordering
        st.divider()
        st.subheader("🧩 Step 2: Context Preview & Reordering")

        active_query = st.session_state.get("compose_query_active", comp_query)
        active_preview = composer.build_context_preview(ordered_selected, query=active_query)
        st.markdown(f"Selected **{len(active_preview.selected_candidates)} message(s)** from **{len(active_preview.source_conversations)} conversation(s)** across **{len(active_preview.source_providers)} provider(s)**:")

        if active_preview.source_providers:
            prov_str = " | ".join(f"**{p}**: {c} msg(s)" for p, c in active_preview.source_providers.items())
            st.caption(f"Provider breakdown: {prov_str}")

        if not active_preview.selected_candidates:
            st.warning("No messages selected. Select at least one candidate message above to form your composed context.")
        else:
            cands_to_display = list(active_preview.selected_candidates)
            for idx, cand in enumerate(cands_to_display):
                c_col1, c_col2, c_col3, c_col4 = st.columns([6, 1, 1, 1])
                with c_col1:
                    role_icon = "👤" if cand.role == "user" else "🤖"
                    st.markdown(f"**#{idx+1} [{cand.source}] {cand.conversation_title} (Msg #{cand.message_index})**")
                    st.markdown(f'<div class="debug-box"><b>{role_icon} {cand.role.title()}:</b> {cand.content}</div>', unsafe_allow_html=True)
                with c_col2:
                    if idx > 0 and st.button("↑", key=f"up_{cand.message_id}_{idx}"):
                        cands_to_display[idx], cands_to_display[idx-1] = cands_to_display[idx-1], cands_to_display[idx]
                        st.session_state["compose_selected_candidates"] = cands_to_display
                        st.rerun()
                with c_col3:
                    if idx < len(cands_to_display) - 1 and st.button("↓", key=f"dn_{cand.message_id}_{idx}"):
                        cands_to_display[idx], cands_to_display[idx+1] = cands_to_display[idx+1], cands_to_display[idx]
                        st.session_state["compose_selected_candidates"] = cands_to_display
                        st.rerun()
                with c_col4:
                    if st.button("✕", key=f"rm_{cand.message_id}_{idx}"):
                        cands_to_display.pop(idx)
                        st.session_state["compose_selected_candidates"] = cands_to_display
                        st.rerun()

            # V5B Destination Integration
            st.divider()
            st.subheader("🔌 Step 3: AI Destination Handoff (V5B)")
            st.caption("🔒 **Local-First & Explicit Privacy**: Choose an AI destination adapter. External transmission requires explicit confirmation.")

            dest_col1, dest_col2 = st.columns([3, 2])
            with dest_col1:
                destination_choice = st.selectbox(
                    "AI Destination Adapter",
                    options=dest_registry.list_provider_names(),
                    index=0,
                    key="v5b_dest_choice"
                )
            with dest_col2:
                if destination_choice == "Local Export (JSON & Plain Text)":
                    st.success("🔒 **Local First**: 100% offline. Zero external network calls.")
                elif destination_choice == "ChatGPT (OpenAI API)":
                    st.info("⚡ **Live API Adapter**: Transmits selected context to OpenAI Chat API.")
                elif destination_choice == "Gemini (Google AI API)":
                    st.info("⚡ **Live API Adapter**: Transmits selected context to Google Gemini API.")
                else:
                    st.warning("⚠️ **Planned Adapter**: Use Local Export, ChatGPT, or Gemini.")

            # Local Export Path
            if destination_choice == "Local Export (JSON & Plain Text)":
                if st.button("📄 Generate Portable Context Package (v1.0)", key="gen_v5a_pkg_btn"):
                    pkg = local_exporter.prepare_context(active_preview)
                    st.session_state["v5a_active_package"] = pkg

                active_pkg = st.session_state.get("v5a_active_package")
                if active_pkg:
                    with st.expander("📦 Inspection & Export Package Payload", expanded=True):
                        st.success(f"Generated `PortableContextPackage` (ID: `{active_pkg.package_id[:8]}...`, Schema: `v{active_pkg.schema_version}`)")

                        tab_text, tab_json, tab_prov = st.tabs(["📄 Plain-Text Context (Markdown)", "📦 Versioned JSON Package (v1.0)", "🔎 Provenance & Metadata"])

                        with tab_text:
                            st.code(active_pkg.context_text, language="markdown")
                            st.download_button(
                                label="💾 Download Plain-Text Context (.txt)",
                                data=active_pkg.context_text,
                                file_name=f"context_{active_pkg.package_id[:8]}.txt",
                                mime="text/plain",
                                key="dl_text_btn"
                            )

                        with tab_json:
                            json_str = active_pkg.to_json()
                            st.code(json_str, language="json")
                            st.download_button(
                                label="💾 Download JSON Package (.json)",
                                data=json_str,
                                file_name=f"package_{active_pkg.package_id[:8]}.json",
                                mime="application/json",
                                key="dl_json_btn"
                            )

                        with tab_prov:
                            st.markdown(f"**Title:** {active_pkg.title}")
                            st.markdown(f"**Topic Query:** `{active_pkg.topic}`")
                            st.markdown(f"**Created At:** {active_pkg.created_at}")
                            st.markdown(f"**Source Providers:** {active_pkg.source_providers}")
                            st.markdown("**Provenance Audit Records:**")
                            st.json(active_pkg.provenance)

            # ChatGPT (OpenAI API) Path
            elif destination_choice == "ChatGPT (OpenAI API)":
                openai_key_input = st.text_input(
                    "OpenAI API Key (or set OPENAI_API_KEY environment variable)",
                    type="password",
                    key="openai_api_key_input",
                    help="Your API key is never hardcoded, logged, or saved to disk."
                )

                if st.button("🔒 Review & Prepare Transfer to ChatGPT", key="review_chatgpt_btn"):
                    pkg = local_exporter.prepare_context(active_preview)
                    st.session_state["v5b_pending_package"] = pkg
                    st.session_state["v5b_pending_dest"] = "ChatGPT (OpenAI API)"
                    st.session_state["v5b_awaiting_confirm"] = True

                awaiting_confirm = st.session_state.get("v5b_awaiting_confirm", False)
                pending_pkg = st.session_state.get("v5b_pending_package")
                pending_dest = st.session_state.get("v5b_pending_dest")

                if awaiting_confirm and pending_pkg and pending_dest == "ChatGPT (OpenAI API)":
                    st.warning("🔒 **Transfer Confirmation & Privacy Gate**")
                    with st.expander("📋 Review Transfer Summary", expanded=True):
                        st.markdown(f"**Destination:** `ChatGPT (OpenAI API)`")
                        st.markdown(f"**Topic:** `{pending_pkg.topic}`")
                        st.markdown(f"**Selected Messages:** `{len(pending_pkg.messages)}`")
                        st.markdown(f"**Source Conversations:** `{len(pending_pkg.source_conversations)}`")
                        st.markdown(f"**Source Providers:** `{pending_pkg.source_providers}`")
                        st.error("⚠️ **Data Leaving Local Environment:**\nOnly the selected messages and topic context will be transmitted to OpenAI API under your API key.")

                        conf_c1, conf_c2 = st.columns(2)
                        with conf_c1:
                            if st.button("❌ Cancel Transfer", key="cancel_transfer_btn"):
                                st.session_state["v5b_awaiting_confirm"] = False
                                st.session_state["v5b_pending_package"] = None
                                st.session_state["v5b_pending_dest"] = None
                                st.rerun()
                        with conf_c2:
                            if st.button("🚀 Confirm & Send to ChatGPT", type="primary", key="confirm_send_chatgpt_btn"):
                                adapter = dest_registry.get_adapter("ChatGPT (OpenAI API)")
                                config = {"api_key": openai_key_input} if openai_key_input else {}
                                result = adapter.execute(pending_pkg, config=config)
                                st.session_state["v5b_transfer_result"] = result
                                st.session_state["v5b_awaiting_confirm"] = False
                                st.rerun()

                transfer_result = st.session_state.get("v5b_transfer_result")
                if transfer_result and transfer_result.provider == "ChatGPT (OpenAI API)":
                    st.divider()
                    if transfer_result.status == "API_RESPONSE":
                        st.success(f"🎉 **{transfer_result.message}**")
                        if transfer_result.response_payload and "response_text" in transfer_result.response_payload:
                            st.markdown("### 🤖 ChatGPT Response:")
                            st.info(transfer_result.response_payload["response_text"])
                    elif transfer_result.status == "AUTH_REQUIRED":
                        st.error(f"🔑 **Authentication Required**: {transfer_result.message}")
                    else:
                        st.error(f"❌ **Transfer Failed [{transfer_result.status}]**: {transfer_result.message}")

            # Gemini (Google AI API) Path
            elif destination_choice == "Gemini (Google AI API)":
                gemini_key_input = st.text_input(
                    "Google Gemini API Key (or set GEMINI_API_KEY environment variable)",
                    type="password",
                    key="gemini_api_key_input",
                    help="Your API key is never hardcoded, logged, or saved to disk."
                )

                if st.button("🔒 Review & Prepare Transfer to Gemini", key="review_gemini_btn"):
                    pkg = local_exporter.prepare_context(active_preview)
                    st.session_state["v5b_pending_package"] = pkg
                    st.session_state["v5b_pending_dest"] = "Gemini (Google AI API)"
                    st.session_state["v5b_awaiting_confirm"] = True

                awaiting_confirm = st.session_state.get("v5b_awaiting_confirm", False)
                pending_pkg = st.session_state.get("v5b_pending_package")
                pending_dest = st.session_state.get("v5b_pending_dest")

                if awaiting_confirm and pending_pkg and pending_dest == "Gemini (Google AI API)":
                    st.warning("🔒 **Transfer Confirmation & Privacy Gate**")
                    with st.expander("📋 Review Transfer Summary", expanded=True):
                        st.markdown(f"**Destination:** `Gemini (Google AI API)`")
                        st.markdown(f"**Topic:** `{pending_pkg.topic}`")
                        st.markdown(f"**Selected Messages:** `{len(pending_pkg.messages)}`")
                        st.markdown(f"**Source Conversations:** `{len(pending_pkg.source_conversations)}`")
                        st.markdown(f"**Source Providers:** `{pending_pkg.source_providers}`")
                        st.error("⚠️ **Data Leaving Local Environment:**\nOnly the selected messages and topic context will be transmitted to Google Gemini API under your API key.")

                        conf_c1, conf_c2 = st.columns(2)
                        with conf_c1:
                            if st.button("❌ Cancel Transfer", key="cancel_transfer_gemini_btn"):
                                st.session_state["v5b_awaiting_confirm"] = False
                                st.session_state["v5b_pending_package"] = None
                                st.session_state["v5b_pending_dest"] = None
                                st.rerun()
                        with conf_c2:
                            if st.button("🚀 Confirm & Send to Gemini", type="primary", key="confirm_send_gemini_btn"):
                                adapter = dest_registry.get_adapter("Gemini (Google AI API)")
                                config = {"api_key": gemini_key_input} if gemini_key_input else {}
                                result = adapter.execute(pending_pkg, config=config)
                                st.session_state["v5b_transfer_result"] = result
                                st.session_state["v5b_awaiting_confirm"] = False
                                st.rerun()

                transfer_result = st.session_state.get("v5b_transfer_result")
                if transfer_result and transfer_result.provider == "Gemini (Google AI API)":
                    st.divider()
                    if transfer_result.status == "API_RESPONSE":
                        st.success(f"🎉 **{transfer_result.message}**")
                        if transfer_result.response_payload and "response_text" in transfer_result.response_payload:
                            st.markdown("### ♊ Gemini Response:")
                            st.info(transfer_result.response_payload["response_text"])
                    elif transfer_result.status == "AUTH_REQUIRED":
                        st.error(f"🔑 **Authentication Required**: {transfer_result.message}")
                    else:
                        st.error(f"❌ **Transfer Failed [{transfer_result.status}]**: {transfer_result.message}")

            # Stub Destinations (Claude)
            else:
                adapter = dest_registry.get_adapter(destination_choice)
                if adapter:
                    res = adapter.validate(None)
                    st.info(f"ℹ️ **{res.provider}**: {res.message}")

            st.divider()
            st.subheader("🚀 Step 4: Create Composed Conversation")

            default_title = f"Composed: {comp_query[:35].title()}" if comp_query else "Composed: Context Strategy"
            comp_title_input = st.text_input("Composed Conversation Title", value=default_title, key="comp_title_input")

            if st.button("🧩 Create Composed Chat", type="primary", key="create_comp_chat_btn"):
                if cands_to_display and comp_title_input:
                    new_conv, comp_ctx = composer.create_composed_conversation(
                        title=comp_title_input,
                        query=comp_query,
                        selected_candidates=cands_to_display,
                    )
                    st.toast(f"🎉 Created composed conversation '{new_conv.title}'!", icon="🧩")
                    st.success(f"Created derived conversation **'{new_conv.title}'** containing {new_conv.message_count} messages from {len(comp_ctx.source_conversations)} source conversation(s)!")
                    if "compose_grouped_results" in st.session_state:
                        del st.session_state["compose_grouped_results"]
                    if "compose_selected_candidates" in st.session_state:
                        del st.session_state["compose_selected_candidates"]
                    if "v5a_active_package" in st.session_state:
                        del st.session_state["v5a_active_package"]
                    st.rerun()


# -----------------------------------------------------------------------------
# VIEW 4: HYBRID SEARCH MEMORY
# -----------------------------------------------------------------------------
elif nav_option == "🔍 Search Memory":
    st.markdown('<div class="main-header">Hybrid Search Memory</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Search by keywords OR describe what you remember in your own words.</div>', unsafe_allow_html=True)

    st.write("💡 **Try searching:**")
    cols = st.columns(3)
    example_queries = [
        "Which idea did I have about not needing to physically inspect something?",
        "I had an idea to prevent a household resource from being wasted because I didn't know its level.",
        "That home automation idea about checking levels remotely",
    ]
    selected_example = ""

    for idx, eq in enumerate(example_queries):
        if cols[idx].button(f"🔍 {eq[:30]}...", key=f"chip_{idx}"):
            selected_example = eq

    query_input = st.text_input(
        "Search Query",
        value=selected_example,
        placeholder="Describe what you discussed...",
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        source_filter = st.selectbox("Filter Source", ["All Sources", "ChatGPT", "Gemini", "Claude", "TXT", "JSON"])
    with col_f2:
        category_filter = st.selectbox("Filter Category", ["All Categories", "Startup Idea", "Learning", "Research", "Project"])

    if query_input:
        src_param = None if source_filter == "All Sources" else source_filter
        cat_param = None if category_filter == "All Categories" else category_filter

        results = search_engine.search(query_input, category=cat_param, source=src_param)

        st.subheader(f"Found {len(results)} Matching Result(s)")

        if not results:
            st.warning("⚠️ No sufficiently relevant memory found for this search description.")
        else:
            for res in results:
                with st.container():
                    st.markdown(f"### 📄 {res.conversation_title} <span class='score-badge'>Match Score: {res.score}%</span>", unsafe_allow_html=True)
                    st.caption(f"Source: {res.source} | Role: {res.matched_role.title()} | Message Index: {res.msg_index}")

                    st.markdown(f"> **Snippet:** ...{res.snippet}...")

                    if DEBUG_SEMANTIC_SEARCH:
                        sem_tuples = search_engine.semantic_engine.search_semantic(query_input, limit=50)
                        raw_sem_score = dict(sem_tuples).get(res.message_id, 0.0)
                        st.markdown(
                            f'<div class="debug-box">🐛 <b>DEBUG SCORES:</b> Raw Neural Semantic Cosine: <b>{raw_sem_score:.4f}</b> | Combined Hybrid: <b>{res.score}%</b></div>',
                            unsafe_allow_html=True
                        )

                    with st.expander("🔍 View Original Source Context (Surrounding Messages)"):
                        context = search_engine.keyword_engine.get_source_context(res.conversation_id, res.msg_index, window=2)

                        if context["previous_messages"]:
                            st.markdown("**Previous Messages:**")
                            for pmsg in context["previous_messages"]:
                                st.markdown(f"*[{pmsg.role.title()}]*: {pmsg.content}")

                        st.markdown("**Matched Message (Source of Truth):**")
                        st.markdown(f'<div class="context-highlight"><b>[{res.matched_role.title()}]</b>: {res.matched_content}</div>', unsafe_allow_html=True)

                        if context["following_messages"]:
                            st.markdown("**Following Messages:**")
                            for fmsg in context["following_messages"]:
                                st.markdown(f"*[{fmsg.role.title()}]*: {fmsg.content}")

                    st.divider()


# -----------------------------------------------------------------------------
# VIEW 5: ASK MY MEMORY
# -----------------------------------------------------------------------------
elif nav_option == "🤖 Ask My Memory":
    st.markdown('<div class="main-header">Ask My Memory</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ask natural questions grounded strictly in your stored conversations.</div>', unsafe_allow_html=True)

    ask_query = st.text_input(
        "Ask a Question",
        placeholder="e.g. Which idea did I have about not needing to physically inspect something?",
    )

    if st.button("🤖 Generate Grounded Answer", type="primary") or ask_query:
        if ask_query:
            answer = assistant.ask(ask_query)

            if answer.found:
                st.success("✅ Information Found in Memory")
                st.markdown("### 🤖 Synthesized Answer")
                st.markdown(answer.summary)

                st.subheader("📚 Source Citations & Evidence")
                for src in answer.formatted_sources:
                    with st.expander(f"[{src['ref_num']}] {src['conversation_title']} ({src['source']}) — Match Score: {src['score']}%"):
                        st.write(f"**Message Index:** {src['message_index']} | **Role:** {src['role'].title()}")
                        st.write(f"**Category:** {src['category']}")
                        st.markdown(f"> *{src['content_snippet']}*")
            else:
                st.warning("⚠️ No sufficiently relevant memory found")
                st.write(answer.summary)


# -----------------------------------------------------------------------------
# VIEW 6: CATEGORIES & TAGS
# -----------------------------------------------------------------------------
elif nav_option == "🏷️ Categories & Tags":
    st.markdown('<div class="main-header">Categories & Tags</div>', unsafe_allow_html=True)

    convs = repo.list_conversations(limit=100)
    all_categories = sorted(list(set(c.category for c in convs if c.category)))
    all_tags = sorted(list(set(t for c in convs for t in c.tags if t)))

    col_cat, col_tag = st.columns(2)

    with col_cat:
        st.subheader("📁 Categories")
        if not all_categories:
            st.info("No categories assigned yet.")
        else:
            for cat in all_categories:
                cat_convs = [c for c in convs if c.category == cat]
                with st.expander(f"📁 {cat} ({len(cat_convs)} conversations)"):
                    for c in cat_convs:
                        st.write(f"• **{c.title}** ({c.source})")

    with col_tag:
        st.subheader("🏷️ Tags")
        if not all_tags:
            st.info("No tags assigned yet.")
        else:
            for tag in all_tags:
                tag_convs = [c for c in convs if tag in c.tags]
                with st.expander(f"🏷️ {tag} ({len(tag_convs)} conversations)"):
                    for c in tag_convs:
                        st.write(f"• **{c.title}** ({c.source})")


# -----------------------------------------------------------------------------
# VIEW 7: DATA & SETTINGS
# -----------------------------------------------------------------------------
elif nav_option == "⚙️ Data & Settings":
    st.markdown('<div class="main-header">Data Management & Privacy</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Full privacy control over your personal memory layer database.</div>', unsafe_allow_html=True)

    db_path = os.path.abspath(os.path.join("data", "memory.db"))
    st.write(f"**Database Location:** `{db_path}`")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🚀 Load Sample Demo Conversations"):
            added = seed_demo_data()
            st.success(f"Added sample conversations with vector embeddings.")
            st.rerun()

    with c2:
        if st.button("🔄 Re-index All Embeddings"):
            stats = search_engine.semantic_engine.reindex_all_embeddings()
            st.success(f"Re-indexed {stats['embeddings_reindexed']} embeddings across {stats['conversations_found']} conversations.")
            st.rerun()

    with c3:
        if st.button("⚠️ Clear Entire Memory Database", type="secondary"):
            convs = repo.list_conversations()
            for c in convs:
                repo.delete_conversation(c.id)
            st.toast("Database cleared!")
            st.rerun()
