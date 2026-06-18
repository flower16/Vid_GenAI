"""Query-time retrieval. NEVER re-ingests — only reads from Pinecone + SQLite."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from llama_index.embeddings.openai import OpenAIEmbedding

from app.config import get_settings
from app.models import Document
from app.rag.pinecone_setup import get_index

settings = get_settings()


def retrieve(
    db: Session,
    question: str,
    top_k: int = 5,
    namespace: Optional[str] = None,
    document_type: Optional[str] = None,
    provider_name: Optional[str] = None,
    plan_name: Optional[str] = None,
) -> dict:
    """Embed the question, query Pinecone with hard filters, enrich with SQLite metadata.

    Always scopes to the Oncor utility area. Returns chunks + source citations.
    """
    namespace = namespace or settings.default_namespace

    # Short-circuit when RAG keys aren't real — avoids slow network failures /
    # retries on placeholder keys. The workflow then keeps conservative defaults.
    _placeholders = {"", "your-openai-key", "your-pinecone-key", "changeme"}
    if (settings.openai_api_key or "").strip() in _placeholders or \
       (settings.pinecone_api_key or "").strip() in _placeholders:
        return {"question": question, "namespace": namespace, "matches": [],
                "status": "rag_disabled"}

    embedder = OpenAIEmbedding(model=settings.embed_model, api_key=settings.openai_api_key)
    qvec = embedder.get_query_embedding(question)

    pine_filter = {"utility_area": {"$eq": settings.utility_area}}
    if document_type:
        pine_filter["document_type"] = {"$eq": document_type}
    if provider_name:
        pine_filter["provider_name"] = {"$eq": provider_name}
    if plan_name:
        pine_filter["plan_name"] = {"$eq": plan_name}

    res = get_index().query(
        vector=qvec, top_k=top_k, namespace=namespace,
        filter=pine_filter, include_metadata=True,
    )

    chunks = []
    for match in res.get("matches", []):
        md = match["metadata"]
        doc = db.query(Document).filter_by(document_id=md.get("document_id")).first()
        chunks.append({
            "score": match["score"],
            "text": md.get("text", ""),
            "page": md.get("page"),
            "citation": {
                "document_id": md.get("document_id"),
                "provider": md.get("provider_name"),
                "plan_name": md.get("plan_name"),
                "document_type": md.get("document_type"),
                "file_name": doc.file_name if doc else None,
                "effective_date": None,
            },
        })

    return {"question": question, "namespace": namespace, "matches": chunks}
