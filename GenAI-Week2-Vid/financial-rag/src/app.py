"""Streamlit front-end for the Financial RAG pipeline.

Run with:  streamlit run src/app.py

Features
--------
* Upload PDF / TXT / DOCX documents and (re)build indexes.
* Choose chunking method (Fixed / Semantic).
* Toggle reranking ON / OFF.
* Ask questions and inspect the answer + retrieved chunks (score + metadata).
* Comparison mode: Fixed vs Semantic answers side-by-side.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Allow ``streamlit run src/app.py`` to resolve the ``src`` package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src.chunking import chunk_documents, chunk_statistics
from src.config import DATA_DIR, SETTINGS
from src.loaders import load_directory, load_uploaded_files
from src.rag_pipeline import build_pipeline
from src.vector_store import build_index, index_exists

st.set_page_config(page_title="Financial RAG", page_icon="📄", layout="wide")


# --------------------------------------------------------------------------- #
# Caching: pipelines are expensive (index load + LLM client).
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_pipeline(method: str, use_reranker: bool):
    return build_pipeline(method=method, use_reranker=use_reranker)


def build_index_for(method: str, documents) -> dict:
    chunks = chunk_documents(documents, method)
    build_index(chunks, method)
    get_pipeline.clear()  # invalidate cached pipelines bound to the old index
    return chunk_statistics(chunks)


# --------------------------------------------------------------------------- #
# Sidebar — ingestion & configuration
# --------------------------------------------------------------------------- #
st.sidebar.title("⚙️ Configuration")

method = st.sidebar.radio("Chunking method", ["fixed", "semantic"], index=0)
use_reranker = st.sidebar.toggle("Reranking (BGE)", value=False)

st.sidebar.divider()
st.sidebar.subheader("📥 Build index")

uploaded = st.sidebar.file_uploader(
    "Upload documents", type=["pdf", "txt", "docx"], accept_multiple_files=True
)

col_a, col_b = st.sidebar.columns(2)

if col_a.button("Index uploads", use_container_width=True, disabled=not uploaded):
    with st.spinner("Loading & indexing uploaded files..."):
        tmp_paths = []
        for uf in uploaded:
            tmp = Path(tempfile.gettempdir()) / uf.name
            tmp.write_bytes(uf.getbuffer())
            tmp_paths.append(tmp)
        docs = load_uploaded_files(tmp_paths)
        stats = build_index_for(method, docs)
    st.sidebar.success(f"Indexed {stats['num_chunks']} {method} chunks.")

if col_b.button("Index samples", use_container_width=True):
    with st.spinner(f"Indexing sample corpus ({method})..."):
        docs = load_directory(DATA_DIR)
        stats = build_index_for(method, docs)
    st.sidebar.success(f"Indexed {stats['num_chunks']} {method} chunks.")


# --------------------------------------------------------------------------- #
# Main panel
# --------------------------------------------------------------------------- #
st.title("📄 Financial Document RAG")
st.caption(
    f"Embeddings: `{SETTINGS.embedding_model}`  |  "
    f"LLM: `{SETTINGS.llm_model}`  |  Reranker: `{SETTINGS.reranker_model}`"
)

comparison_mode = st.checkbox("🔀 Comparison mode (Fixed vs Semantic)", value=False)
question = st.text_input("Ask a question about your financial documents:")


def render_chunks(chunks):
    for i, c in enumerate(chunks, 1):
        score = c.rerank_score if c.rerank_score is not None else c.score
        label = "rerank" if c.rerank_score is not None else "similarity"
        with st.expander(f"[{i}] {c.source}  —  {label}: {score:.4f}"):
            st.write(c.text)
            st.json(c.metadata, expanded=False)


def answer_with(method_: str, reranker_: bool):
    if not index_exists(method_):
        st.warning(f"No `{method_}` index yet — build it from the sidebar.")
        return
    pipe = get_pipeline(method_, reranker_)
    result = pipe.answer(question)
    st.markdown("#### Answer")
    st.success(result.answer)
    st.markdown(f"#### Retrieved chunks ({len(result.chunks)})")
    render_chunks(result.chunks)


if question:
    if comparison_mode:
        left, right = st.columns(2)
        with left:
            st.subheader("Fixed chunking")
            answer_with("fixed", use_reranker)
        with right:
            st.subheader("Semantic chunking")
            answer_with("semantic", use_reranker)
    else:
        st.subheader(f"{method.title()} chunking · reranker {'ON' if use_reranker else 'OFF'}")
        answer_with(method, use_reranker)
else:
    st.info("Build an index (sidebar) and ask a question to get started.")
