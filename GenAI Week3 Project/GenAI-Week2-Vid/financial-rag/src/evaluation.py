"""Evaluation harness.

Two families of metrics:

1. Retrieval metrics (computed locally, no LLM):
     * Precision@k
     * Recall@k
     * MRR (Mean Reciprocal Rank)
   Relevance is judged at the *document* level: a retrieved chunk counts as
   relevant if its source document is in the question's ``relevant_docs`` list.

2. Answer-quality metrics via RAGAS:
     * Faithfulness
     * Answer Relevancy
     * Context Precision
     * Context Recall

The eval set lives in ``eval/questions.json``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.config import EVAL_DIR, SETTINGS
from src.rag_pipeline import RAGResult


# --------------------------------------------------------------------------- #
# Eval-set loading
# --------------------------------------------------------------------------- #
@dataclass
class EvalQuestion:
    id: str
    category: str
    question: str
    ground_truth: str
    relevant_docs: list[str]


def load_eval_questions(path: str | Path | None = None) -> list[EvalQuestion]:
    path = Path(path) if path else EVAL_DIR / "questions.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalQuestion(**q) for q in data]


# --------------------------------------------------------------------------- #
# Retrieval metrics
# --------------------------------------------------------------------------- #
def _is_relevant(chunk_metadata: dict, relevant_docs: list[str]) -> bool:
    doc = chunk_metadata.get("document", "")
    return any(rd.lower() in doc.lower() for rd in relevant_docs)


def precision_at_k(result: RAGResult, relevant_docs: list[str], k: int) -> float:
    top = result.chunks[:k]
    if not top:
        return 0.0
    hits = sum(_is_relevant(c.metadata, relevant_docs) for c in top)
    return hits / len(top)


def recall_at_k(result: RAGResult, relevant_docs: list[str], k: int) -> float:
    if not relevant_docs:
        return 0.0
    top = result.chunks[:k]
    retrieved_docs = {
        c.metadata.get("document", "").lower()
        for c in top
        if _is_relevant(c.metadata, relevant_docs)
    }
    return min(1.0, len(retrieved_docs) / len(set(d.lower() for d in relevant_docs)))


def reciprocal_rank(result: RAGResult, relevant_docs: list[str]) -> float:
    for rank, chunk in enumerate(result.chunks, start=1):
        if _is_relevant(chunk.metadata, relevant_docs):
            return 1.0 / rank
    return 0.0


def retrieval_metrics(
    results: list[tuple[EvalQuestion, RAGResult]], k: int | None = None
) -> dict:
    """Aggregate Precision@k, Recall@k and MRR across the eval set."""
    k = k or SETTINGS.retrieval.eval_k
    if not results:
        return {"precision@k": 0.0, "recall@k": 0.0, "mrr": 0.0, "k": k, "n": 0}

    p = [precision_at_k(r, q.relevant_docs, k) for q, r in results]
    rec = [recall_at_k(r, q.relevant_docs, k) for q, r in results]
    rr = [reciprocal_rank(r, q.relevant_docs) for q, r in results]
    n = len(results)
    return {
        "precision@k": round(sum(p) / n, 4),
        "recall@k": round(sum(rec) / n, 4),
        "mrr": round(sum(rr) / n, 4),
        "k": k,
        "n": n,
    }


# --------------------------------------------------------------------------- #
# RAGAS answer-quality metrics
# --------------------------------------------------------------------------- #
def ragas_metrics(results: list[tuple[EvalQuestion, RAGResult]]) -> dict:
    """Run RAGAS over the answered eval set.

    Imported lazily because RAGAS pulls in heavy deps and makes LLM calls; we do
    not want to require it just to compute the local retrieval metrics.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:  # pragma: no cover
        return {"error": f"RAGAS not available: {exc}"}

    records = {
        "question": [q.question for q, _ in results],
        "answer": [r.answer for _, r in results],
        "contexts": [r.contexts for _, r in results],
        "ground_truth": [q.ground_truth for q, _ in results],
    }
    dataset = Dataset.from_dict(records)
    scores = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    df = scores.to_pandas()
    return {
        "faithfulness": round(float(df["faithfulness"].mean()), 4),
        "answer_relevancy": round(float(df["answer_relevancy"].mean()), 4),
        "context_precision": round(float(df["context_precision"].mean()), 4),
        "context_recall": round(float(df["context_recall"].mean()), 4),
    }


def evaluate_experiment(
    results: list[tuple[EvalQuestion, RAGResult]],
    run_ragas: bool = True,
) -> dict:
    """Full metric bundle for one experiment configuration."""
    out = {"retrieval": retrieval_metrics(results)}
    if run_ragas:
        out["ragas"] = ragas_metrics(results)
    return out
