"""Chunking strategies: fixed-size (Strategy A) and semantic (Strategy B).

Both strategies emit ``Document`` chunks carrying the metadata required by the
spec — document name, page number and a unique ``chunk_id`` — so that the two
indexes are directly comparable downstream.
"""
from __future__ import annotations

from typing import Literal

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import SETTINGS

ChunkingMethod = Literal["fixed", "semantic"]


def _assign_chunk_ids(chunks: list[Document], method: str) -> list[Document]:
    """Stamp a stable, globally-unique chunk id onto each chunk."""
    for i, chunk in enumerate(chunks):
        doc_name = chunk.metadata.get("document", "unknown")
        chunk.metadata["chunk_id"] = f"{method}-{doc_name}-{i:05d}"
        chunk.metadata["chunk_index"] = i
        chunk.metadata["chunk_method"] = method
        chunk.metadata["chunk_len"] = len(chunk.page_content)
    return chunks


def fixed_size_chunk(documents: list[Document]) -> list[Document]:
    """Strategy A — RecursiveCharacterTextSplitter (size=500, overlap=50)."""
    cfg = SETTINGS.chunking
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    return _assign_chunk_ids(chunks, "fixed")


def semantic_chunk(documents: list[Document]) -> list[Document]:
    """Strategy B — embedding-aware semantic chunking.

    Imported lazily so that the fixed-size path (and unit tests) do not require
    network access or an OpenAI key.
    """
    from langchain_experimental.text_splitter import SemanticChunker

    from src.embeddings import get_embeddings

    cfg = SETTINGS.chunking
    splitter = SemanticChunker(
        embeddings=get_embeddings(),
        breakpoint_threshold_type=cfg.breakpoint_threshold_type,
        breakpoint_threshold_amount=cfg.breakpoint_threshold_amount,
    )
    chunks = splitter.split_documents(documents)
    return _assign_chunk_ids(chunks, "semantic")


def chunk_documents(documents: list[Document], method: ChunkingMethod) -> list[Document]:
    """Dispatch to the requested chunking strategy."""
    if method == "fixed":
        return fixed_size_chunk(documents)
    if method == "semantic":
        return semantic_chunk(documents)
    raise ValueError(f"Unknown chunking method: {method!r}")


def chunk_statistics(chunks: list[Document]) -> dict:
    """Summary stats used by the comparison report."""
    lengths = [len(c.page_content) for c in chunks]
    n = len(lengths)
    return {
        "num_chunks": n,
        "avg_chunk_len": round(sum(lengths) / n, 1) if n else 0.0,
        "min_chunk_len": min(lengths) if n else 0,
        "max_chunk_len": max(lengths) if n else 0,
    }
