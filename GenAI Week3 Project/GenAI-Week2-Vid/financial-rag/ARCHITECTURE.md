# Architecture — Financial RAG Pipeline

This document describes the system design: components, data flow, the experiment
matrix, and the key engineering decisions behind each layer.

---

## 1. High-level overview

The system is a modular Retrieval-Augmented Generation (RAG) pipeline that
ingests financial documents, indexes them under **two competing chunking
strategies**, and answers questions through an optional **cross-encoder
reranking** stage before LLM generation. An evaluation harness scores every
configuration so the strategies can be compared head-to-head.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            INGESTION (offline)                             │
│                                                                            │
│   data/*/             loaders.py          chunking.py        embeddings.py │
│  ┌──────────┐        ┌──────────┐        ┌────────────┐      ┌───────────┐ │
│  │ PDF/TXT/ │  ───►  │ normalise│  ───►  │  fixed  ┐  │ ───► │  OpenAI   │ │
│  │  DOCX    │        │ metadata │        │ semantic┘  │      │ embeddings│ │
│  └──────────┘        └──────────┘        └────────────┘      └─────┬─────┘ │
│                                                                    ▼       │
│                                              vector_store.py  ┌──────────┐ │
│                                              (FAISS)          │ 2 indexes│ │
│                                                               │ fixed /  │ │
│                                                               │ semantic │ │
│                                                               └──────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
┌──────────────────────────────────────┼─────────────────────────────────────┐
│                            QUERY-TIME │ (online)                             │
│                                       ▼                                      │
│   question     retrieval.py        reranker.py          rag_pipeline.py      │
│  ┌────────┐   ┌─────────────┐     ┌─────────────┐      ┌──────────────────┐  │
│  │  user  │─► │ Top-K = 10  │ ──► │ BGE cross-  │ ───► │ prompt + ChatLLM │  │
│  │  query │   │ similarity  │     │ encoder →5  │      │  → grounded ans. │  │
│  └────────┘   └─────────────┘     └─────────────┘      └────────┬─────────┘  │
│                    (rerank optional; bypassed → trim to 5)      ▼            │
│                                                          answer + chunks     │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  app.py (Streamlit UI)     run_experiments.py (A–D)        evaluation.py
  upload / ask / compare    builds report + results.json   retrieval + RAGAS
```

---

## 2. Component responsibilities

Each module has one job and a narrow interface, so any layer can be swapped
without touching the others.

| Module | Responsibility | Key in / out |
|---|---|---|
| [`config.py`](src/config.py) | Single source of truth for paths, model names, and all hyper-parameters (`chunk_size`, `top_k`, …). `.env`-overridable. | — |
| [`loaders.py`](src/loaders.py) | Load PDF/TXT/DOCX into LangChain `Document`s with a **uniform metadata schema** (`document`, `page`, `doc_type`, `source`). | files → `list[Document]` |
| [`chunking.py`](src/chunking.py) | Two strategies — fixed-size (`RecursiveCharacterTextSplitter`) and semantic (`SemanticChunker`). Stamps `chunk_id` and chunk stats. | `Document`s → chunked `Document`s |
| [`embeddings.py`](src/embeddings.py) | Cached OpenAI embedding factory (`text-embedding-3-large`, swappable). | text → vectors |
| [`vector_store.py`](src/vector_store.py) | FAISS create / save / load / query. One persisted index per strategy. Converts L2 distance → bounded similarity. | chunks ↔ FAISS index |
| [`retrieval.py`](src/retrieval.py) | Top-K similarity search → `RetrievedChunk(text, score, metadata)`, the shared result shape. | query → `list[RetrievedChunk]` |
| [`reranker.py`](src/reranker.py) | `BAAI/bge-reranker-large` cross-encoder scores (query, chunk) pairs; Top-10 → Top-5. | query + chunks → reranked chunks |
| [`rag_pipeline.py`](src/rag_pipeline.py) | Orchestrates retrieve → (rerank) → prompt → `ChatOpenAI`. Returns `RAGResult`. | question → answer + chunks |
| [`evaluation.py`](src/evaluation.py) | Retrieval metrics (P@k, R@k, MRR) + RAGAS answer-quality metrics. | answered Qs → metric dict |
| [`app.py`](src/app.py) | Streamlit UI: ingest, configure, ask, compare. | — |
| [`run_experiments.py`](run_experiments.py) | Runs experiments A–D, writes `comparison_report.md` + `results.json`. | — |

---

## 3. Data contracts

Two small, stable shapes flow through the whole system. Keeping them fixed is
what lets the UI, the experiment runner, and the evaluator consume identical
objects.

**Chunk metadata** (set in `loaders.py`, extended in `chunking.py`):

```python
{
  "source":      "<absolute path>",
  "document":    "acme_corp_10k_2023.txt",
  "page":        3,            # 1-based for PDFs, None otherwise
  "doc_type":    "sec_filings",
  "chunk_id":    "fixed-acme_corp_10k_2023.txt-00012",
  "chunk_index": 12,
  "chunk_method":"fixed",
  "chunk_len":   498,
}
```

**`RetrievedChunk`** (retrieval → reranker → RAG → UI/eval):

```python
RetrievedChunk(
  text:         str,
  score:        float,          # vector similarity (pre-rerank), in [0,1]
  metadata:     dict,           # the chunk metadata above
  rerank_score: float | None,   # filled only when reranking runs
)
```

**`RAGResult`** (pipeline output): `question, answer, chunks, method, reranked`,
plus a `.contexts` helper that yields plain strings in the shape RAGAS expects.

---

## 4. Query-time sequence

```
User question
   │
   ▼
RAGPipeline.answer(q)
   │
   ├─► retrieve(store, q, k=10)                  # FAISS similarity search
   │        └─ returns 10 RetrievedChunk
   │
   ├─► if use_reranker:                          # Experiments B / D
   │        rerank(q, chunks, top_n=5)           # BGE cross-encoder → best 5
   │   else:                                     # Experiments A / C
   │        chunks[:5]                           # trim to same final-k (fair)
   │
   ├─► _format_context(chunks)                   # numbered, source-tagged blocks
   │
   ├─► ChatOpenAI.invoke(PROMPT_TEMPLATE)        # "answer only from context …"
   │
   ▼
RAGResult(answer, chunks, …)                     # consumed by UI + evaluator
```

The prompt instructs the model to answer **only** from the supplied context and
to return `"Information not found in provided documents."` when the answer is
absent — the guardrail that keeps answers grounded and makes faithfulness
measurable.

---

## 5. Experiment matrix

The same pipeline runs in four configurations to isolate the two variables
(chunking strategy × reranking):

| Experiment | Chunking | Reranking | What it isolates |
|---|---|---|---|
| **A** | Fixed | Off | Baseline |
| **B** | Fixed | On | Reranking lift on fixed chunks |
| **C** | Semantic | Off | Chunking-strategy effect |
| **D** | Semantic | On | Combined best case |

Comparisons of interest: **A→B** and **C→D** isolate reranking; **A→C** and
**B→D** isolate the chunking strategy.

---

## 6. Evaluation design

Two independent metric families:

- **Retrieval metrics** (local, no LLM): Precision@5, Recall@5, MRR. Relevance is
  judged at the **document level** — a retrieved chunk is relevant if its source
  document is in the question's `relevant_docs` label
  ([`eval/questions.json`](eval/questions.json), 23 labelled questions). Cheap,
  deterministic, and reproducible.
- **Answer-quality metrics** (RAGAS, LLM-judged): Faithfulness, Answer
  Relevancy, Context Precision, Context Recall. Loaded lazily so the retrieval
  metrics never require RAGAS or extra token spend.

---

## 7. Key design decisions

1. **Two persisted FAISS indexes, not one.** Fixed and semantic chunks live in
   separate indexes (`indexes/faiss_fixed`, `indexes/faiss_semantic`) so the
   strategies are compared on identical queries with zero cross-contamination,
   and the UI's comparison mode just loads both.
2. **Config centralisation.** Every magic number lives in `config.py` dataclasses.
   Experiments are reproducible and a model/embedding swap is a one-line change.
3. **Lazy heavy imports.** `SemanticChunker`, the BGE cross-encoder, and RAGAS
   are imported inside the functions that need them — the fixed-size path and
   unit-style checks run without a GPU, network, or API key.
4. **Distance → similarity normalisation.** FAISS returns L2 distance; we map it
   to `1/(1+d) ∈ (0,1]` so scores are display-friendly and comparable.
5. **Fair non-reranked baseline.** Experiments A/C still trim Top-10 → Top-5, so
   all four configs generate from the same number of context chunks; only the
   *selection* mechanism differs.
6. **Shared result objects.** `RetrievedChunk` / `RAGResult` are the only shapes
   crossing module boundaries, so UI, runner, and evaluator never reshape data.
7. **Cached resources.** Embedding clients, the reranker model, and Streamlit
   pipelines are cached (`lru_cache` / `st.cache_resource`) to avoid reloading
   weights and re-reading the API key on every call.

---

## 8. Technology stack

| Concern | Choice | Notes |
|---|---|---|
| Orchestration | LangChain | loaders, splitters, vector-store wrappers |
| Embeddings | OpenAI `text-embedding-3-large` | alt: `-3-small` via `.env` |
| Vector store | FAISS (CPU) | local, file-persisted; ChromaDB optional |
| Reranker | `BAAI/bge-reranker-large` | sentence-transformers CrossEncoder, CPU |
| LLM | `gpt-4o-mini` (default) | temperature 0 for deterministic answers |
| Evaluation | RAGAS + custom retrieval metrics | RAGAS optional/lazy |
| UI | Streamlit | upload, configure, ask, compare |

---

## 9. Extending the system

- **New document type** → add a loader branch in `loaders.py`; the rest is
  type-agnostic.
- **New chunking strategy** → add a function in `chunking.py` and a branch in
  `chunk_documents`; register an index name in `config.py`.
- **Different vector DB** (e.g. ChromaDB) → reimplement the four functions in
  `vector_store.py`; nothing upstream changes.
- **Different reranker / LLM** → swap the model id in `config.py` / `.env`.
