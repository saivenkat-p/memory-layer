"""
Personal AI Memory Layer - Streamlit Web Application MVP with Hybrid Search.

Main entry point integrating Conversation Parsing, Database Storage,
Hybrid Search Engine (Keyword + Vector Embeddings), Source Context Viewer, and Ask My Memory Assistant.
"""

import os
import streamlit as st
from app.repositories.database import Database
from app.repositories.conversation_repository import ConversationRepository
from app.parsers.factory import parse_conversation_file
from app.parsers.base import ParsingError
from app.search.hybrid_search import HybridSearchEngine
from app.ai.memory_assistant import AskMyMemoryAssistant

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
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_services():
    """Initializes singletons for Database, Repository, HybridSearchEngine, and Assistant."""
    db = Database(os.path.join("data", "memory.db"))
    repo = ConversationRepository(db)
    search_engine = HybridSearchEngine(repo)
    assistant = AskMyMemoryAssistant(search_engine)
    return repo, search_engine, assistant


repo, search_engine, assistant = get_services()


# Sidebar Navigation
st.sidebar.title("🧠 Memory Layer")
st.sidebar.markdown("*Don't remember WHERE. Search WHAT you discussed.*")
st.sidebar.divider()

nav_option = st.sidebar.radio(
    "Navigation",
    options=[
        "📊 Dashboard",
        "📥 Import Conversation",
        "💬 Conversations",
        "🔍 Search Memory",
        "🤖 Ask My Memory",
        "🏷️ Categories & Tags",
        "⚙️ Data & Settings",
    ],
)


# Helper function to seed sample data
def seed_demo_data():
    sample_files = [
        ("data/sample_chatgpt.json", "sample_chatgpt.json"),
        ("data/sample_chat.txt", "sample_chat.txt"),
    ]
    added = 0
    for path, name in sample_files:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                conv = parse_conversation_file(content, name)
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
            st.success(f"Successfully loaded {added} sample conversations! Refreshing...")
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
# VIEW 2: IMPORT CONVERSATION
# -----------------------------------------------------------------------------
elif nav_option == "📥 Import Conversation":
    st.markdown('<div class="main-header">Import Conversation</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload chat exports (.json or .txt) from ChatGPT, Gemini, Claude, or custom logs.</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Select conversation file", type=["json", "txt", "md"])

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
                st.toast("Conversation saved successfully with vector embeddings!", icon="🎉")
                st.success("Saved! You can now search for topics discussed in this conversation.")

        except ParsingError as e:
            st.error(f"❌ Failed to parse file: {e}")


# -----------------------------------------------------------------------------
# VIEW 3: CONVERSATIONS LIST
# -----------------------------------------------------------------------------
elif nav_option == "💬 Conversations":
    st.markdown('<div class="main-header">Stored Conversations</div>', unsafe_allow_html=True)

    convs = repo.list_conversations(limit=100)

    if not convs:
        st.info("No conversations stored yet. Use the 'Import Conversation' tab or load sample data from Dashboard.")
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
                with c2:
                    if st.button("🗑️ Delete", key=f"del_{conv.id}", type="secondary"):
                        repo.delete_conversation(conv.id)
                        st.rerun()

                st.divider()
                st.markdown("### Conversation History")
                for msg in conv.messages:
                    role_class = "chat-user" if msg.role == "user" else "chat-assistant"
                    st.markdown(f'<div class="{role_class}"><b>{msg.role.title()}:</b> {msg.content}</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# VIEW 4: HYBRID SEARCH MEMORY
# -----------------------------------------------------------------------------
elif nav_option == "🔍 Search Memory":
    st.markdown('<div class="main-header">Hybrid Search Memory</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Search by keywords OR describe what you remember in your own words.</div>', unsafe_allow_html=True)

    # Example prompt chips
    st.write("💡 **Try searching:**")
    cols = st.columns(4)
    example_queries = [
        "water tank",
        "automatically stop motor when tank is full",
        "climbing mountain prototype",
        "avoiding going upstairs to check the water"
    ]
    selected_example = ""

    for idx, eq in enumerate(example_queries):
        if cols[idx].button(f"🔍 {eq[:22]}...", key=f"chip_{idx}"):
            selected_example = eq

    query_input = st.text_input(
        "Search Query",
        value=selected_example,
        placeholder="Describe what you discussed (e.g., avoiding going upstairs to check the water)...",
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

        for res in results:
            with st.container():
                st.markdown(f"### 📄 {res.conversation_title} <span class='score-badge'>Match Score: {res.score}%</span>", unsafe_allow_html=True)
                st.caption(f"Source: {res.source} | Role: {res.matched_role.title()} | Message Index: {res.msg_index}")

                st.markdown(f"> **Snippet:** ...{res.snippet}...")

                # Feature 5: Source Context Expander
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
        placeholder="e.g. What startup ideas did I discuss? Or where did I talk about Qiskit?",
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
                st.warning("⚠️ No Stored Information Found")
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

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 Load Sample Demo Conversations"):
            added = seed_demo_data()
            st.success(f"Added {added} sample conversations with vector embeddings.")
            st.rerun()

    with c2:
        if st.button("⚠️ Clear Entire Memory Database", type="secondary"):
            convs = repo.list_conversations()
            for c in convs:
                repo.delete_conversation(c.id)
            st.toast("Database cleared!")
            st.rerun()
