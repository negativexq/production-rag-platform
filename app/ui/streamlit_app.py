"""Minimal Streamlit chat UI: upload a PDF, ask a question, watch the
answer stream in with page/paragraph citations highlighted and a grounding
check surfaced. Runs on the host (not containerized) — see
docs/PLANNING.md Sprint 11 closing note for why.

Run with: make ui   (equivalent to `streamlit run app/ui/streamlit_app.py`)
"""

import os

import httpx
import streamlit as st

from app.ui.citation_formatting import highlight_citations
from app.ui.ingest_helper import ingest_uploaded_file
from app.ui.sse_client import parse_sse_lines

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Production RAG Platform", page_icon="📄")
st.title("📄 Production RAG Platform")

if "messages" not in st.session_state:
    st.session_state.messages = []  # list[{"role": str, "content": str}]

with st.sidebar:
    st.header("Ingest a PDF")
    uploaded_file = st.file_uploader("Choose a PDF", type="pdf")
    if uploaded_file is not None and st.button("Ingest"):
        with st.spinner(f"Ingesting {uploaded_file.name}..."):
            stats = ingest_uploaded_file(uploaded_file.name, uploaded_file.getvalue())
        st.success(
            f"Upserted {stats.chunks_upserted} chunk(s) from {stats.files_processed} file(s)."
        )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(highlight_citations(message["content"]))

question = st.chat_input("Ask a question about the ingested documents")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer_parts: list[str] = []
        grounding_event: dict | None = None

        # Real token-by-token streaming: the placeholder is updated inside
        # the loop as each SSE event arrives, not after the whole response
        # is collected.
        with httpx.stream(
            "POST", f"{BACKEND_URL}/chat", json={"question": question}, timeout=120.0
        ) as response:
            for event in parse_sse_lines(response.iter_lines()):
                if event.event == "message":
                    answer_parts.append(event.data["token"])
                    placeholder.markdown(highlight_citations("".join(answer_parts)) + "▌")
                elif event.event == "grounding":
                    grounding_event = event.data

        full_answer = "".join(answer_parts)
        placeholder.markdown(highlight_citations(full_answer))

        if grounding_event is not None:
            if grounding_event["grounded"]:
                st.caption(f"✅ Grounded — citations: {grounding_event['citations_found']}")
            else:
                st.warning(
                    "⚠️ Some citations in this answer could not be verified against the "
                    f"retrieved context: {grounding_event['ungrounded_citations']}"
                )

    st.session_state.messages.append({"role": "assistant", "content": full_answer})
