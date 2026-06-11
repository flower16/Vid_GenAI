"""Document loaders for the Financial RAG pipeline.

Supports PDF, TXT and DOCX. Every loader returns a list of LangChain
``Document`` objects with a consistent metadata schema:

    {
        "source":   "<absolute path>",
        "document": "<file name>",
        "page":     <int | None>,      # 1-based page for PDFs, None otherwise
        "doc_type": "<sec_filings | earnings_calls | ...>",
    }

``doc_type`` is inferred from the parent ``data/<category>/`` folder when present.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx"}


def _infer_doc_type(path: Path) -> str:
    """Use the immediate parent directory name as the document category."""
    parent = path.parent.name
    return parent if parent else "unknown"


def _normalise_metadata(doc: Document, path: Path) -> Document:
    """Force every Document onto the shared metadata schema."""
    page = doc.metadata.get("page")
    # PyPDFLoader pages are 0-based; make them human-friendly (1-based).
    if isinstance(page, int):
        page = page + 1
    doc.metadata = {
        "source": str(path.resolve()),
        "document": path.name,
        "page": page,
        "doc_type": _infer_doc_type(path),
    }
    return doc


def load_file(file_path: str | Path) -> list[Document]:
    """Load a single PDF / TXT / DOCX file into normalised Documents."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(path)

    ext = path.suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(str(path))
    elif ext == ".txt":
        loader = TextLoader(str(path), encoding="utf-8")
    elif ext == ".docx":
        loader = Docx2txtLoader(str(path))
    else:
        raise ValueError(f"Unsupported file type: {ext!r} ({path.name})")

    docs = loader.load()
    return [_normalise_metadata(d, path) for d in docs]


def load_directory(directory: str | Path, recursive: bool = True) -> list[Document]:
    """Load every supported document under ``directory``."""
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(root)

    pattern = "**/*" if recursive else "*"
    documents: list[Document] = []
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                documents.extend(load_file(path))
            except Exception as exc:  # noqa: BLE001 - keep ingesting other files
                print(f"[loaders] skipping {path.name}: {exc}")
    return documents


def load_uploaded_files(file_paths: Iterable[str | Path]) -> list[Document]:
    """Convenience wrapper used by the Streamlit upload widget."""
    documents: list[Document] = []
    for fp in file_paths:
        documents.extend(load_file(fp))
    return documents


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    from src.config import DATA_DIR

    docs = load_directory(DATA_DIR)
    print(f"Loaded {len(docs)} document pages from {DATA_DIR}")
    for d in docs[:3]:
        print(d.metadata, "->", d.page_content[:80].replace("\n", " "))
