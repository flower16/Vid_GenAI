"""FAISS vector-store wrapper: create / save / load / query.

One index is kept per chunking strategy (``fixed`` and ``semantic``) under
``indexes/``, satisfying the spec's "store separate indexes" requirement.
"""
from __future__ import annotations

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from src.config import INDEX_DIR, INDEX_NAMES
from src.embeddings import get_embeddings


def build_index(chunks: list[Document], method: str) -> FAISS:
    """Create a FAISS index from chunks and persist it to disk."""
    if not chunks:
        raise ValueError("Cannot build an index from zero chunks.")
    store = FAISS.from_documents(chunks, get_embeddings())
    save_index(store, method)
    return store


def index_path(method: str) -> Path:
    name = INDEX_NAMES.get(method)
    if name is None:
        raise ValueError(f"Unknown index method: {method!r}")
    return INDEX_DIR / name


def save_index(store: FAISS, method: str) -> Path:
    path = index_path(method)
    store.save_local(str(path))
    return path


def load_index(method: str) -> FAISS:
    """Load a previously persisted FAISS index."""
    path = index_path(method)
    if not path.exists():
        raise FileNotFoundError(
            f"No index found at {path}. Build it first with run_experiments.py "
            f"or the Streamlit app."
        )
    # We created these indexes ourselves, so deserialization is trusted.
    return FAISS.load_local(
        str(path),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )


def index_exists(method: str) -> bool:
    return index_path(method).exists()


def query_index(
    store: FAISS, query: str, k: int = 10
) -> list[tuple[Document, float]]:
    """Top-k similarity search returning (Document, similarity_score) pairs.

    FAISS returns an L2 distance, so we convert to a bounded similarity score in
    [0, 1] where higher is better, which is friendlier for display and metrics.
    """
    results = store.similarity_search_with_score(query, k=k)
    converted: list[tuple[Document, float]] = []
    for doc, distance in results:
        similarity = 1.0 / (1.0 + float(distance))
        converted.append((doc, similarity))
    return converted
