"""One-time PDF ingestion with SHA-256 deduplication.

Dedup contract (per spec):
    if SHA-256(file) already in `documents`:
        return existing document_id; SKIP parse / chunk / embed.
    else:
        parse -> chunk (LlamaIndex) -> embed -> upsert Pinecone
        -> write Document + DocumentChunk rows -> mark complete.

A PDF is only re-embedded if its content (hash) changes.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from llama_index.core import Document as LIDocument
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.file import PDFReader

from app.config import get_settings
from app.models import Document, DocumentChunk, IngestionJob
from app.rag.pinecone_setup import ensure_index

settings = get_settings()


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #
def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Metadata tagging (cheap heuristics; can be swapped for an LLM tagger)
# --------------------------------------------------------------------------- #
def _tag_chunk(text: str) -> dict:
    t = text.lower()
    return {
        "mentions_tdu_offset": any(k in t for k in
                                   ("tdu", "delivery charge", "tdsp", "utility charge")),
        "mentions_free_nights": "free night" in t or "free weekend" in t,
    }


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def ingest_pdf(
    db: Session,
    file_path: str,
    file_name: str,
    document_type: str,
    provider_name: Optional[str] = None,
    plan_name: Optional[str] = None,
    namespace: Optional[str] = None,
) -> dict:
    """Ingest a single PDF exactly once. Returns a status dict."""
    namespace = namespace or settings.default_namespace
    file_hash = sha256_of_file(file_path)

    # ---- 1) DEDUP CHECK ---------------------------------------------------- #
    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        return {
            "status": "skipped_duplicate",
            "document_id": existing.document_id,
            "file_hash": file_hash,
            "message": "Identical content already ingested; parse/chunk/embed skipped.",
        }

    # ---- 2) Register document + job (status=processing) -------------------- #
    document_id = str(uuid.uuid4())
    doc = Document(
        document_id=document_id,
        file_name=file_name,
        file_hash=file_hash,
        provider_name=provider_name,
        plan_name=plan_name,
        document_type=document_type,
        utility_area=settings.utility_area,
        pinecone_namespace=namespace,
        ingestion_status="processing",
        stored_path=file_path,
        upload_date=datetime.utcnow(),
    )
    job = IngestionJob(document_id=document_id, status="running")
    db.add_all([doc, job])
    db.commit()

    try:
        # ---- 3) Parse PDF ONCE -------------------------------------------- #
        pages = PDFReader().load_data(file=file_path)  # list[LIDocument], 1 per page
        full_docs = [
            LIDocument(
                text=p.text,
                metadata={
                    "document_id": document_id,
                    "provider_name": provider_name or "",
                    "plan_name": plan_name or "",
                    "document_type": document_type,
                    "utility_area": settings.utility_area,
                    "page": p.metadata.get("page_label") or (i + 1),
                },
            )
            for i, p in enumerate(pages)
        ]

        # ---- 4) Chunk (LlamaIndex) ---------------------------------------- #
        splitter = SentenceSplitter(
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
        )
        nodes = splitter.get_nodes_from_documents(full_docs)

        # ---- 5) Embed ----------------------------------------------------- #
        embedder = OpenAIEmbedding(model=settings.embed_model,
                                   api_key=settings.openai_api_key)
        texts = [n.get_content() for n in nodes]
        vectors = embedder.get_text_embedding_batch(texts, show_progress=False)

        # ---- 6) Upsert to Pinecone (document_id in metadata; filterable) -- #
        index = ensure_index()
        pine_vectors = []
        chunk_rows = []
        for i, (node, emb) in enumerate(zip(nodes, vectors)):
            vector_id = f"{document_id}:{i}"
            tags = _tag_chunk(node.get_content())
            meta = {
                "document_id": document_id,
                "provider_name": provider_name or "",
                "plan_name": plan_name or "",
                "document_type": document_type,
                "utility_area": settings.utility_area,
                "page": node.metadata.get("page", 0),
                "chunk_index": i,
                "text": node.get_content()[:1500],  # for retrieval display
                **tags,
            }
            pine_vectors.append({"id": vector_id, "values": emb, "metadata": meta})
            chunk_rows.append(DocumentChunk(
                document_id=document_id, chunk_index=i, vector_id=vector_id,
                text=node.get_content(), page=meta["page"], **tags,
            ))

        # batch upsert
        for start in range(0, len(pine_vectors), 100):
            index.upsert(vectors=pine_vectors[start:start + 100], namespace=namespace)

        # ---- 7) Persist chunk refs + mark complete ------------------------ #
        db.add_all(chunk_rows)
        doc.chunk_count = len(chunk_rows)
        doc.ingestion_status = "complete"
        job.status = "complete"
        job.finished_at = datetime.utcnow()
        job.detail = f"Embedded {len(chunk_rows)} chunks into '{namespace}'."
        db.commit()

        return {
            "status": "complete",
            "document_id": document_id,
            "file_hash": file_hash,
            "chunks": len(chunk_rows),
            "namespace": namespace,
        }

    except Exception as e:  # noqa: BLE001
        db.rollback()
        doc = db.query(Document).filter_by(document_id=document_id).first()
        if doc:
            doc.ingestion_status = "error"
        job = db.query(IngestionJob).filter_by(document_id=document_id).order_by(
            IngestionJob.id.desc()).first()
        if job:
            job.status = "error"
            job.detail = str(e)
            job.finished_at = datetime.utcnow()
        db.commit()
        return {"status": "error", "document_id": document_id, "error": str(e)}
