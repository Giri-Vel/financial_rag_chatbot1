"""
RegulatorAI - Streamlit Frontend
===================================
Chat interface for querying Indian financial regulations.
WhatsApp-style chat bubbles — user right, assistant left.
No avatars, no sidebar, clean terminal aesthetic.

Usage:
    streamlit run ui/app.py
"""

import os
import streamlit as st
import requests
from datetime import datetime


# ── Page Config ────────────────────────────────────────

st.set_page_config(
    page_title="RegulatorAI — RBI/SEBI Terminal",
    page_icon="📟",
    layout="wide",
)

# ── Constants ──────────────────────────────────────────

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
TOP_K = 5  # Hardcoded for now — conscious decision, revisit later

TOPIC_LABELS = {
    "digital_lending": "Digital Lending",
    "kyc_aml": "KYC / AML",
    "payment_systems": "Payment Systems",
}


# ── Theme CSS ─────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Share+Tech+Mono&display=swap');

html, body, [class*="st-"] {
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { visibility: hidden; }

/* ── Constrain main content width ──────────── */
[data-testid="stMainBlockContainer"],
.block-container {
    max-width: 900px !important;
    margin: 0 auto !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* ── Header styles ─────────────────────────── */
.term-title {
    font-family: 'Share Tech Mono', monospace;
    color: #33ff33;
    font-size: 1.5rem;
    letter-spacing: 0.12em;
    text-shadow: 0 0 8px #33ff3333;
    margin-bottom: 0.1rem;
}

.term-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    color: #667766;
    font-size: 0.72rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
}

.term-status {
    font-family: 'IBM Plex Mono', monospace;
    color: #339933;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    padding: 0.3rem 0;
    border-top: 1px solid #1a331a;
    border-bottom: 1px solid #1a331a;
    margin: 0.3rem 0 0.5rem 0;
}

.term-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    color: #667766;
    margin-top: 0.4rem;
}

.term-footer {
    font-size: 0.58rem;
    color: #556655;
    letter-spacing: 0.1em;
    text-align: center;
    margin-top: 1rem;
}

/* ── Chat bubble styles ────────────────────── */
.chat-container {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 0.5rem 0;
}

.bubble-row {
    display: flex;
    width: 100%;
}

.bubble-row.user {
    justify-content: flex-end;
}

.bubble-row.assistant {
    justify-content: flex-start;
}

.bubble {
    max-width: 82%;
    padding: 0.8rem 1rem;
    border-radius: 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    line-height: 1.65;
    word-wrap: break-word;
}

.bubble.user {
    background: #1a3a1a;
    color: #ccddcc;
    border-bottom-right-radius: 4px;
    border: 1px solid #2a4a2a;
}

.bubble.assistant {
    background: #141e14;
    color: #ccddcc;
    border-bottom-left-radius: 4px;
    border: 1px solid #1a331a;
}

.bubble strong {
    color: #33ff33;
}

.bubble code {
    color: #ffb833;
    background: rgba(255, 184, 51, 0.1);
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    font-size: 0.82rem;
}

.bubble ul, .bubble ol {
    margin: 0.3rem 0;
    padding-left: 1.2rem;
}

.bubble li {
    margin-bottom: 0.2rem;
}

/* ── Source styles ──────────────────────────── */
.source-block {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #aaccaa;
    background: #0a140a;
    border: 1px solid #1a331a;
    border-radius: 6px;
    padding: 0.7rem;
    margin-top: 0.5rem;
}

.source-item {
    margin-bottom: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1a331a;
}

.source-item:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
}

.source-title {
    color: #33cccc;
    font-weight: 500;
}

.source-detail {
    color: #667766;
    font-size: 0.65rem;
}

details summary {
    cursor: pointer;
    color: #33cccc;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    margin-top: 0.4rem;
}

details summary:hover {
    color: #55eeee;
}
</style>
""", unsafe_allow_html=True)


# ── API Helpers ────────────────────────────────────────

@st.cache_data(ttl=30)
def api_health() -> dict | None:
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=60)
def api_topics() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/topics", timeout=5)
        resp.raise_for_status()
        return resp.json().get("topics", [])
    except Exception:
        return []


@st.cache_data(ttl=60)
def api_documents() -> dict:
    try:
        resp = requests.get(f"{API_BASE}/documents", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"documents": [], "total_documents": 0, "total_chunks": 0}


def api_query(question: str, topic: str | None) -> dict | None:
    try:
        payload = {"question": question, "top_k": TOP_K}
        if topic:
            payload["topic"] = topic
        resp = requests.post(f"{API_BASE}/query", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── Document count per topic ───────────────────────────

def get_topic_doc_counts() -> dict:
    """Count unique documents per topic from the /documents endpoint."""
    docs_data = api_documents()
    counts = {}
    for doc in docs_data.get("documents", []):
        topic = doc.get("topic", "unknown")
        counts[topic] = counts.get(topic, 0) + 1
    return counts


# ── Source Display ─────────────────────────────────────

def render_sources_html(sources: list[dict]) -> str:
    if not sources:
        return ""

    items_html = ""
    for i, src in enumerate(sources, 1):
        similarity_pct = int(src.get("similarity", 0) * 100)
        items_html += (
            f'<div class="source-item">'
            f'<span class="source-title">[{i}] {src["title"]}</span><br/>'
            f'<span class="source-detail">'
            f'Section: {src.get("section", "N/A")} · '
            f'Date: {src.get("date", "N/A")} · '
            f'Type: {src.get("doc_type", "N/A")} · '
            f'Match: {similarity_pct}%'
            f'</span></div>'
        )

    return (
        f'<details>'
        f'<summary>Sources ({len(sources)} documents cited)</summary>'
        f'<div class="source-block">{items_html}</div>'
        f'</details>'
    )


# ── Chat Rendering ────────────────────────────────────

def render_user_bubble(text: str) -> str:
    """Render a right-aligned user message bubble."""
    import html as html_mod
    escaped = html_mod.escape(text)
    return (
        f'<div class="bubble-row user">'
        f'<div class="bubble user">{escaped}</div>'
        f'</div>'
    )


def render_assistant_bubble(result: dict) -> str:
    """Render a left-aligned assistant message bubble with sources."""
    answer = result.get("answer", result.get("content", ""))

    # Convert markdown bold to HTML (basic conversion)
    import re
    answer_html = answer
    answer_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', answer_html)
    answer_html = re.sub(r'`(.+?)`', r'<code>\1</code>', answer_html)

    # Convert markdown lists
    lines = answer_html.split('\n')
    processed = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- '):
            if not in_list:
                processed.append('<ul>')
                in_list = True
            processed.append(f'<li>{stripped[2:]}</li>')
        else:
            if in_list:
                processed.append('</ul>')
                in_list = False
            if stripped:
                processed.append(f'<p style="margin: 0.3rem 0;">{stripped}</p>')
            else:
                processed.append('<br/>')
    if in_list:
        processed.append('</ul>')

    answer_html = '\n'.join(processed)

    # Sources
    sources_html = ""
    sources = result.get("sources", [])
    if sources:
        sources_html = render_sources_html(sources)

    # Meta
    meta_html = ""
    model = result.get("model", "")
    context_used = result.get("context_used", 0)
    if model:
        meta_html = (
            f'<div class="term-meta">'
            f'Model: {model} · Chunks: {context_used} · '
            f'{datetime.now().strftime("%H:%M:%S")}'
            f'</div>'
        )

    return (
        f'<div class="bubble-row assistant">'
        f'<div class="bubble assistant">'
        f'{answer_html}'
        f'{sources_html}'
        f'{meta_html}'
        f'</div>'
        f'</div>'
    )


def render_all_messages():
    """Render all messages as HTML chat bubbles."""
    if not st.session_state.messages:
        return

    html_parts = ['<div class="chat-container">']

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            html_parts.append(render_user_bubble(msg["content"]))
        else:
            html_parts.append(render_assistant_bubble(msg))

    html_parts.append('</div>')

    st.markdown('\n'.join(html_parts), unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────

def main():
    # ── Header ──
    st.markdown('<div class="term-title">RegulatorAI</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="term-subtitle">'
        f'RBI & SEBI Regulatory Document Analysis · {datetime.now().strftime("%d %b %Y").upper()}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── System status ──
    health = api_health()
    if health:
        st.markdown(
            f'<div class="term-status">'
            f'● Online · {health["collection_size"]} chunks · '
            f'LLM: {health["model"]} · '
            f'Embeddings: {health["embedding_model"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.error("API offline — run: `uvicorn src.api.main:app --port 8000`")

    # ── Topic filter ──
    topic_doc_counts = get_topic_doc_counts()
    topic_options = {"All Topics": None}
    for topic_key, label in TOPIC_LABELS.items():
        doc_count = topic_doc_counts.get(topic_key, 0)
        if doc_count > 0:
            topic_options[f"{label} ({doc_count} docs)"] = topic_key

    selected_label = st.selectbox(
        "Filter by topic",
        options=list(topic_options.keys()),
        index=0,
    )
    selected_topic = topic_options[selected_label]

    st.divider()

    # ── Chat history ──
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "**System initialized.**\n\n"
                "I have access to RBI regulatory documents covering "
                "**Digital Lending**, **KYC/AML**, and **Payment Systems**.\n\n"
                "Ask me anything about Indian financial regulations — "
                "all answers include citations from official documents.\n\n"
                "**Try asking:**\n"
                "- What are the guidelines for digital lending apps?\n"
                "- Explain the V-CIP process for KYC verification\n"
                "- What are the capital requirements for payment aggregators?"
            ),
            "sources": [],
        }]

    # ── Pending query handling ──
    # If there's a pending query (user message added, awaiting API response),
    # show all messages including user's, then fetch and add the response.
    if st.session_state.get("pending_query"):
        query_info = st.session_state.pending_query

        # Render messages so far (includes the user's new message)
        render_all_messages()

        # Show loading indicator
        st.markdown(
            '<div class="bubble-row assistant">'
            '<div class="bubble assistant" style="color: #339933;">'
            '● Querying regulatory documents...'
            '</div></div>',
            unsafe_allow_html=True,
        )

        # Call API
        result = api_query(query_info["question"], query_info["topic"])

        if result and "error" not in result:
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["answer"],
                "sources": result.get("sources", []),
                "model": result.get("model", ""),
                "context_used": result.get("context_used", 0),
            })
        else:
            error_msg = result.get("error", "Unknown error") if result else "API unreachable"
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error: {error_msg}",
                "sources": [],
            })

        # Clear pending state and rerun to show final result
        del st.session_state.pending_query
        st.rerun()
    else:
        # Normal render — no pending query
        render_all_messages()

    # ── Chat input ──
    if prompt := st.chat_input("Enter your regulatory query..."):
        # Add user message to history immediately
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Set pending query flag — next rerun will show user message + loading
        st.session_state.pending_query = {
            "question": prompt,
            "topic": selected_topic,
        }

        # Rerun to show user message immediately
        st.rerun()

    # ── Footer ──
    st.markdown(
        f'<div class="term-footer">'
        f'RegulatorAI v0.1.0 · © 2026 Giri · '
        f'Session {datetime.now().strftime("%Y%m%d.%H%M")}'
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()