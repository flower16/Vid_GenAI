"""FastAPI ingestion + retrieval endpoints.

POST /rag/ingest   -> one-time PDF ingestion (dedup by SHA-256)
GET  /rag/documents-> list ingested docs
POST /rag/query    -> answer from existing vectors (no re-ingestion)
"""
import os

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Document
from app.rag.ingest import ingest_pdf, sha256_of_bytes
from app.rag.retriever import retrieve

settings = get_settings()
router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    document_type: str = Form(...),          # efl|provider_terms|buyback|tdu|bill
    provider_name: str | None = Form(None),
    plan_name: str | None = Form(None),
    namespace: str | None = Form(None),
    db: Session = Depends(get_db),
):
    data = await file.read()
    file_hash = sha256_of_bytes(data)

    # Fast-path dedup BEFORE writing to disk: identical content already ingested.
    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        return {
            "status": "skipped_duplicate",
            "document_id": existing.document_id,
            "file_hash": file_hash,
            "message": "PDF already ingested — parse/chunk/embed skipped.",
        }

    os.makedirs(settings.upload_dir, exist_ok=True)
    dest = os.path.join(settings.upload_dir, f"{file_hash}.pdf")
    with open(dest, "wb") as f:
        f.write(data)

    return ingest_pdf(
        db=db, file_path=dest, file_name=file.filename,
        document_type=document_type, provider_name=provider_name,
        plan_name=plan_name, namespace=namespace,
    )


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.upload_date.desc()).all()
    return [
        {
            "document_id": d.document_id, "file_name": d.file_name,
            "file_hash": d.file_hash, "provider_name": d.provider_name,
            "plan_name": d.plan_name, "document_type": d.document_type,
            "namespace": d.pinecone_namespace, "status": d.ingestion_status,
            "chunks": d.chunk_count, "upload_date": d.upload_date.isoformat(),
        }
        for d in docs
    ]


@router.post("/query")
def query(
    question: str = Form(...),
    top_k: int = Form(5),
    document_type: str | None = Form(None),
    provider_name: str | None = Form(None),
    plan_name: str | None = Form(None),
    namespace: str | None = Form(None),
    db: Session = Depends(get_db),
):
    return retrieve(
        db=db, question=question, top_k=top_k, namespace=namespace,
        document_type=document_type, provider_name=provider_name, plan_name=plan_name,
    )
