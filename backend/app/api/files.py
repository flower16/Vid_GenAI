"""File upload endpoints: bill PDF + solar/SMT CSV.

Upload returns an opaque `file_id` (a filename inside upload_dir) plus a parse
preview. The client passes file_ids back to /compare; the server resolves them
to paths — clients never supply raw filesystem paths (path-traversal guard).
"""
import hashlib
import json
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.ingest.files import parse_bill_pdf, load_smt_csv, load_solar_csv
from app.models import UploadedFile, User

settings = get_settings()
router = APIRouter(prefix="/files", tags=["files"])

KINDS = {"bill": ".pdf", "solar": ".csv", "smt": ".csv"}
MAX_BYTES = 15 * 1024 * 1024  # 15 MB cap


def resolve(file_id: str | None, db: Session, user_id: int) -> str | None:
    """Resolve a file_id to its stored path IF it belongs to this user, else None.

    Ownership is checked against the DB — a user cannot reference another user's
    upload by guessing its file_id.
    """
    if not file_id:
        return None
    row = (db.query(UploadedFile)
           .filter(UploadedFile.file_id == os.path.basename(file_id),
                   UploadedFile.user_id == user_id).first())
    if row and row.stored_path and os.path.exists(row.stored_path):
        return row.stored_path
    return None


@router.get("")
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List the current user's uploaded files, newest first."""
    rows = (db.query(UploadedFile)
            .filter(UploadedFile.user_id == user.id)
            .order_by(UploadedFile.created_at.desc()).all())
    return [{
        "file_id": r.file_id, "kind": r.kind, "original_name": r.original_name,
        "parse_status": r.parse_status, "sha256": r.sha256[:12] if r.sha256 else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/{kind}")
async def upload(kind: str, file: UploadFile = File(...),
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (15 MB max)")

    sha256 = hashlib.sha256(data).hexdigest()

    # Dedup per user: identical content already uploaded -> return the existing row.
    existing = (db.query(UploadedFile)
                .filter(UploadedFile.sha256 == sha256,
                        UploadedFile.kind == kind,
                        UploadedFile.user_id == user.id).first())
    if existing:
        return {"file_id": existing.file_id, "kind": kind,
                "original_name": existing.original_name,
                "preview": json.loads(existing.parsed_json or "null"),
                "status": "skipped_duplicate"}

    os.makedirs(settings.upload_dir, exist_ok=True)
    file_id = f"{uuid.uuid4().hex}_{kind}{KINDS[kind]}"
    dest = os.path.join(settings.upload_dir, file_id)
    with open(dest, "wb") as f:
        f.write(data)

    # Immediate parse preview so the UI can confirm the file was understood.
    parse_status, error = "ok", None
    try:
        if kind == "bill":
            preview = parse_bill_pdf(dest)
        elif kind == "solar":
            preview = load_solar_csv(dest)
        else:
            preview = load_smt_csv(dest)
    except Exception as e:  # noqa: BLE001
        preview, parse_status, error = {"error": str(e)}, "error", str(e)

    db.add(UploadedFile(
        file_id=file_id, user_id=user.id, kind=kind,
        original_name=file.filename, stored_path=dest, sha256=sha256,
        parse_status=parse_status, parsed_json=json.dumps(preview), error=error,
    ))
    db.commit()

    return {"file_id": file_id, "kind": kind,
            "original_name": file.filename, "preview": preview, "status": parse_status}
