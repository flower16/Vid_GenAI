"""Cross-encoder reranking stage using ``BAAI/bge-reranker-large``.

Pipeline per the spec:
    1. Retrieve Top-10 candidates (vector search).
    2. Score every (query, chunk) pair with the cross-encoder.
    3. Sort by reranker score, descending.
    4. Return the Top-5.

The model is loaded lazily and cached so the (heavy) weights are only pulled
once per process.
"""
from __future__ import annotations

from functools import lru_cache

from src.config import SETTINGS
from src.retrieval import RetrievedChunk


@lru_cache(maxsize=1)
def _get_cross_encoder():
    """Load the BGE reranker once. Heavy import kept local on purpose."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(SETTINGS.reranker_model)


def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int | None = None,
) -> list[RetrievedChunk]:
    """Reorder ``chunks`` by cross-encoder relevance and keep the best ``top_n``."""
    if not chunks:
        return []
    top_n = top_n or SETTINGS.retrieval.rerank_top_n

    model = _get_cross_encoder()
    pairs = [(query, c.text) for c in chunks]
    scores = model.predict(pairs)

    for chunk, score in zip(chunks, scores):
        chunk.rerank_score = float(score)

    ranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
    return ranked[:top_n]
