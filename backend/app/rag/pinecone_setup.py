"""Pinecone index bootstrap + handle accessor."""
from functools import lru_cache

from pinecone import Pinecone, ServerlessSpec

from app.config import get_settings

settings = get_settings()


@lru_cache
def get_pinecone() -> Pinecone:
    return Pinecone(api_key=settings.pinecone_api_key)


def ensure_index():
    """Create the index once if it does not exist."""
    pc = get_pinecone()
    existing = {i["name"] for i in pc.list_indexes()}
    if settings.pinecone_index not in existing:
        pc.create_index(
            name=settings.pinecone_index,
            dimension=settings.embed_dim,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.pinecone_cloud,
                                region=settings.pinecone_region),
        )
    return pc.Index(settings.pinecone_index)


def get_index():
    return get_pinecone().Index(settings.pinecone_index)
