"""Top-K retrieval layer.

Wraps the FAISS store and exposes a small ``RetrievedChunk`` dataclass so the
rest of the pipeline (reranker, RAG, evaluation, UI) shares one shape for a
retrieved result: text, score and metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from src.config import SETTINGS
from src.vector_store import query_index


@dataclass
class RetrievedChunk:
    text: str
    score: float                      # vector similarity (pre-rerank)
    metadata: dict
    rerank_score: float | None = None  # filled in by the reranker stage

    @property
    def chunk_id(self) -> str:
        return self.metadata.get("chunk_id", "unknown")

    @property
    def source(self) -> str:
        doc = self.metadata.get("document", "unknown")
        page = self.metadata.get("page")
        return f"{doc} (p.{page})" if page else doc

    @classmethod
    def from_doc(cls, doc: Document, score: float) -> "RetrievedChunk":
        return cls(text=doc.page_content, score=float(score), metadata=dict(doc.metadata))


def retrieve(store: FAISS, query: str, k: int | None = None) -> list[RetrievedChunk]:
    """Return the Top-K most similar chunks for ``query``."""
    k = k or SETTINGS.retrieval.top_k
    hits = query_index(store, query, k=k)
    return [RetrievedChunk.from_doc(doc, score) for doc, score in hits]
