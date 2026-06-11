"""Run the four experiments (A–D) and generate the comparison report.

    Experiment A: Fixed     chunking, no reranking
    Experiment B: Fixed     chunking, with reranking
    Experiment C: Semantic  chunking, no reranking
    Experiment D: Semantic  chunking, with reranking

Usage:
    python run_experiments.py                 # full run (builds indexes + RAGAS)
    python run_experiments.py --no-ragas      # skip the (slow) RAGAS stage
    python run_experiments.py --skip-build    # reuse existing indexes
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from src.chunking import chunk_documents, chunk_statistics
from src.config import DATA_DIR, REPORTS_DIR, SETTINGS
from src.evaluation import evaluate_experiment, load_eval_questions
from src.loaders import load_directory
from src.rag_pipeline import build_pipeline
from src.vector_store import build_index, index_exists

EXPERIMENTS = [
    ("A", "fixed", False),
    ("B", "fixed", True),
    ("C", "semantic", False),
    ("D", "semantic", True),
]


def build_indexes() -> dict:
    """Build the fixed and semantic indexes, returning chunk statistics."""
    print(f"Loading documents from {DATA_DIR} ...")
    documents = load_directory(DATA_DIR)
    print(f"  -> {len(documents)} document pages")

    stats = {}
    for method in ("fixed", "semantic"):
        print(f"Chunking + indexing [{method}] ...")
        chunks = chunk_documents(documents, method)
        build_index(chunks, method)
        stats[method] = chunk_statistics(chunks)
        print(f"  -> {stats[method]}")
    # Lightweight corpus description for the report.
    doc_types = {}
    for d in documents:
        doc_types[d.metadata.get("doc_type", "unknown")] = (
            doc_types.get(d.metadata.get("doc_type", "unknown"), 0) + 1
        )
    stats["_corpus"] = {
        "num_source_pages": len(documents),
        "doc_types": doc_types,
        "unique_documents": len({d.metadata.get("document") for d in documents}),
    }
    return stats


def run_experiment(label: str, method: str, reranker: bool, run_ragas: bool) -> dict:
    print(f"\n=== Experiment {label}: {method} chunking, reranker={'ON' if reranker else 'OFF'} ===")
    pipe = build_pipeline(method=method, use_reranker=reranker)
    questions = load_eval_questions()

    answered = []
    for q in questions:
        result = pipe.answer(q.question)
        answered.append((q, result))
        print(f"  [{q.id}] {q.question[:60]}...")

    metrics = evaluate_experiment(answered, run_ragas=run_ragas)
    print(f"  retrieval: {metrics['retrieval']}")
    if "ragas" in metrics:
        print(f"  ragas:     {metrics['ragas']}")
    return {"label": label, "method": method, "reranker": reranker, "metrics": metrics}


def _fmt(d: dict, key: str) -> str:
    return f"{d.get(key, 'n/a')}" if not isinstance(d.get(key), float) else f"{d[key]:.4f}"


def render_report(
    chunk_stats: dict, runs: list[dict], findings_body: str | None = None
) -> str:
    corpus = chunk_stats.get("_corpus", {})
    lines = [
        "# Financial RAG — Comparison Report",
        "",
        f"_Generated: {date.today().isoformat()}_",
        "",
        "## 1. Dataset Description",
        "",
        f"- **Unique documents:** {corpus.get('unique_documents', 'n/a')}",
        f"- **Source pages/sections:** {corpus.get('num_source_pages', 'n/a')}",
        f"- **Document types:** {', '.join(corpus.get('doc_types', {}).keys())}",
        "",
        "| Document type | Pages/sections |",
        "|---|---|",
    ]
    for dt, n in corpus.get("doc_types", {}).items():
        lines.append(f"| {dt} | {n} |")

    lines += [
        "",
        "## 2. Chunk Statistics",
        "",
        "| Strategy | # Chunks | Avg length | Min | Max |",
        "|---|---|---|---|---|",
    ]
    for method in ("fixed", "semantic"):
        s = chunk_stats.get(method, {})
        lines.append(
            f"| {method} | {s.get('num_chunks','-')} | {s.get('avg_chunk_len','-')} "
            f"| {s.get('min_chunk_len','-')} | {s.get('max_chunk_len','-')} |"
        )

    lines += [
        "",
        "## 3. Retrieval Results",
        "",
        f"_k = {SETTINGS.retrieval.eval_k}_",
        "",
        "| Exp | Chunking | Reranker | Precision@k | Recall@k | MRR |",
        "|---|---|---|---|---|---|",
    ]
    for r in runs:
        ret = r["metrics"]["retrieval"]
        lines.append(
            f"| {r['label']} | {r['method']} | {'ON' if r['reranker'] else 'OFF'} "
            f"| {ret['precision@k']} | {ret['recall@k']} | {ret['mrr']} |"
        )

    lines += [
        "",
        "## 4. Answer Evaluation (RAGAS)",
        "",
        "| Exp | Faithfulness | Answer Relevancy | Context Precision | Context Recall |",
        "|---|---|---|---|---|",
    ]
    for r in runs:
        rg = r["metrics"].get("ragas", {})
        lines.append(
            f"| {r['label']} | {_fmt(rg,'faithfulness')} | {_fmt(rg,'answer_relevancy')} "
            f"| {_fmt(rg,'context_precision')} | {_fmt(rg,'context_recall')} |"
        )

    lines += ["", "## 5. Findings", "", findings_body or FINDINGS_PLACEHOLDER, ""]
    return "\n".join(lines)


FINDINGS_PLACEHOLDER = "\n".join(
    [
        "> Fill in after reviewing the tables above. Prompts to address:",
        "",
        "- **Fixed vs Semantic chunking:** Which strategy retrieved more relevant",
        "  context? Did semantic chunking's variable-length chunks help on dense",
        "  filings vs. short loan clauses?",
        "- **Impact of reranking:** Compare A→B and C→D. Did the BGE cross-encoder",
        "  improve Precision@k / MRR and downstream faithfulness?",
        "- **Computational tradeoffs:** Semantic chunking costs extra embedding calls",
        "  at ingest; reranking adds cross-encoder latency per query. Quantify if",
        "  possible.",
        "- **Recommended production architecture:** State the configuration you would",
        "  ship and why.",
    ]
)


def extract_findings(path) -> str | None:
    """Return a hand-written Findings section so re-runs don't clobber it.

    Returns ``None`` if the file is missing or the section is still the
    placeholder, in which case the placeholder is regenerated.
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    marker = "## 5. Findings"
    if marker not in text:
        return None
    body = text.split(marker, 1)[1].strip()
    if not body or body.startswith("> Fill in after reviewing"):
        return None
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ragas", action="store_true", help="skip RAGAS metrics")
    parser.add_argument("--skip-build", action="store_true", help="reuse existing indexes")
    args = parser.parse_args()

    if args.skip_build and index_exists("fixed") and index_exists("semantic"):
        print("Reusing existing indexes (chunk stats unavailable).")
        chunk_stats = {"fixed": {}, "semantic": {}, "_corpus": {}}
    else:
        chunk_stats = build_indexes()

    runs = [
        run_experiment(label, method, rr, run_ragas=not args.no_ragas)
        for label, method, rr in EXPERIMENTS
    ]

    out_path = REPORTS_DIR / "comparison_report.md"
    findings = extract_findings(out_path)  # preserve hand-written findings
    report = render_report(chunk_stats, runs, findings_body=findings)
    out_path.write_text(report, encoding="utf-8")
    if findings:
        print("Preserved existing hand-written Findings section.")

    json_path = REPORTS_DIR / "results.json"
    json_path.write_text(json.dumps(runs, indent=2), encoding="utf-8")

    print(f"\nReport written to {out_path}")
    print(f"Raw results written to {json_path}")


if __name__ == "__main__":
    main()
