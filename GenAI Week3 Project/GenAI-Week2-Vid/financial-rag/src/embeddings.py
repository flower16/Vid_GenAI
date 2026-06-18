"""Modular embedding factory.

Keeps the embedding model behind a single function so that swapping
``text-embedding-3-large`` for ``text-embedding-3-small`` (or any other backend)
is a one-line change for the whole pipeline.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from src.config import SETTINGS, require_api_key


@lru_cache(maxsize=4)
def get_embeddings(model: str | None = None) -> OpenAIEmbeddings:
    """Return a cached OpenAIEmbeddings client for ``model``.

    Caching avoids re-instantiating clients (and re-reading the API key) every
    time chunking or retrieval needs an embedder.
    """
    require_api_key()
    return OpenAIEmbeddings(model=model or SETTINGS.embedding_model)


def embed_query(text: str, model: str | None = None) -> list[float]:
    return get_embeddings(model).embed_query(text)


def embed_documents(texts: list[str], model: str | None = None) -> list[list[float]]:
    return get_embeddings(model).embed_documents(texts)
