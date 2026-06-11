"""Central configuration for the Financial RAG pipeline.

All tunable knobs live here so that experiments are reproducible and the rest of
the codebase never hard-codes magic numbers. Values can be overridden via
environment variables (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
INDEX_DIR = ROOT_DIR / "indexes"
REPORTS_DIR = ROOT_DIR / "reports"
EVAL_DIR = ROOT_DIR / "eval"

# Sub-corpora that ship with the project.
DATA_SUBDIRS = ("sec_filings", "earnings_calls", "insurance_claims", "loan_docs")

for _d in (INDEX_DIR, REPORTS_DIR, EVAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_MODEL_ALT = "text-embedding-3-small"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-large")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# --------------------------------------------------------------------------- #
# Pipeline hyper-parameters
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size: int = 500
    chunk_overlap: int = 50
    # Semantic chunker boundary sensitivity.
    breakpoint_threshold_type: str = "percentile"
    breakpoint_threshold_amount: float = 95.0


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 10          # candidates pulled from the vector store
    rerank_top_n: int = 5    # kept after reranking
    eval_k: int = 5          # k used for Precision@k / Recall@k


@dataclass(frozen=True)
class Settings:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    embedding_model: str = EMBEDDING_MODEL
    llm_model: str = LLM_MODEL
    reranker_model: str = RERANKER_MODEL


SETTINGS = Settings()

# Index names — one per chunking strategy.
INDEX_NAMES = {
    "fixed": "faiss_fixed",
    "semantic": "faiss_semantic",
}


def require_api_key() -> str:
    """Fail loudly if the OpenAI key is missing rather than deep in a call."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return OPENAI_API_KEY
