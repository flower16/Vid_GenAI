# Financial RAG Pipeline

A Retrieval-Augmented Generation system that answers questions from financial
documents (SEC filings, earnings-call transcripts, insurance policies, loan
agreements) and **compares retrieval strategies**:

1. **Fixed-size chunking** (`RecursiveCharacterTextSplitter`, size 500 / overlap 50)
2. **Semantic chunking** (`SemanticChunker`, embedding-aware boundaries)

…with an optional **BGE cross-encoder reranking** stage, and a full
**evaluation harness** (Precision@5, Recall@5, MRR + RAGAS faithfulness,
answer relevancy, context precision/recall).

---

## Architecture

> Full design write-up — components, data contracts, query-time sequence,
> experiment matrix, and design decisions — is in
> [ARCHITECTURE.md](ARCHITECTURE.md). Quick view:

```
            ┌─────────────┐   ┌────────────┐   ┌──────────────┐
documents → │  loaders.py │ → │ chunking.py│ → │ embeddings.py│
            └─────────────┘   └────────────┘   └──────┬───────┘
                                                      ▼
   query ──────────────────────────────────► ┌────────────────┐
                                              │ vector_store.py│  (FAISS, 1 index
                                              └────────┬───────┘   per strategy)
                                                       ▼
                                              ┌────────────────┐
                                              │  retrieval.py  │  Top-K = 10
                                              └────────┬───────┘
                                                       ▼
                                              ┌────────────────┐
                                              │  reranker.py   │  BGE → Top-5
                                              └────────┬───────┘
                                                       ▼
                                              ┌────────────────┐
                                              │ rag_pipeline.py│  LLM answer
                                              └────────────────┘
   evaluation.py  ◄── run_experiments.py (A/B/C/D) ──►  reports/comparison_report.md
   app.py (Streamlit UI)
```

## Project structure

```
financial-rag/
├── data/                     # sample corpus (one file per document type)
│   ├── sec_filings/
│   ├── earnings_calls/
│   ├── insurance_claims/
│   └── loan_docs/
├── src/
│   ├── config.py             # all hyper-parameters & paths
│   ├── loaders.py            # PDF / TXT / DOCX loaders
│   ├── chunking.py           # fixed + semantic chunking
│   ├── embeddings.py         # OpenAI embedding factory
│   ├── vector_store.py       # FAISS create/save/load/query
│   ├── retrieval.py          # Top-K retrieval
│   ├── reranker.py           # BAAI/bge-reranker-large
│   ├── rag_pipeline.py       # retrieve → rerank → generate
│   ├── evaluation.py         # retrieval metrics + RAGAS
│   └── app.py                # Streamlit UI
├── eval/questions.json       # 22 labelled evaluation questions
├── reports/comparison_report.md
├── notebooks/evaluation.ipynb
├── scripts/                  # Windows setup & run helpers (.ps1 / .bat)
├── run_experiments.py        # runs experiments A–D, writes the report
├── requirements.txt
├── ARCHITECTURE.md           # full system design write-up
└── README.md
```

## Setup

### Windows (recommended — one command)

From the project root in **PowerShell**:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `.venv`, installs everything, and scaffolds `.env`. Then edit
`.env`, set `OPENAI_API_KEY=sk-...`, and run:

```powershell
.\.venv\Scripts\Activate.ps1            # activate the environment
python run_experiments.py               # or: streamlit run src\app.py
```

Helper scripts (all live in [`scripts/`](scripts/)):

| Script | Purpose |
|---|---|
| `scripts\setup.ps1` | create venv + install deps + scaffold `.env` |
| `scripts\run_app.ps1` | launch the Streamlit app |
| `scripts\run_experiments.ps1 [-NoRagas] [-SkipBuild]` | run experiments A–D |
| `scripts\setup.bat` | same setup, for plain **CMD** users |

> **PowerShell execution policy.** If `Activate.ps1` is blocked
> (`running scripts is disabled on this system`), either run the scripts with
> `-ExecutionPolicy Bypass` as shown above, or allow signed local scripts once
> per user:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> Alternatively use CMD and `.\.venv\Scripts\activate.bat`.

### Windows / macOS / Linux (manual)

```bash
# 1. create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1       # Windows PowerShell
# .venv\Scripts\activate.bat     # Windows CMD
# source .venv/bin/activate      # macOS / Linux

# 2. install dependencies
pip install -r requirements.txt

# 3. configure your OpenAI key
copy .env.example .env           # Windows  (cp on macOS/Linux)
#  …then edit .env and set OPENAI_API_KEY=sk-...
```

> The first run downloads the `BAAI/bge-reranker-large` weights (~1.3 GB) the
> first time reranking is used.

### Windows troubleshooting

- **`python` not found / wrong version.** Install Python 3.11+ from
  [python.org](https://www.python.org/downloads/) and tick *"Add python.exe to
  PATH"*. Verify with `python --version`. If `python` opens the Microsoft Store,
  disable the App-execution alias (Settings → Apps → Advanced app settings → App
  execution aliases) or use the `py -3.11` launcher.
- **`faiss-cpu` install fails.** It ships prebuilt wheels for Python 3.11/3.12
  on Windows — make sure pip is current (`python -m pip install --upgrade pip`).
  Python 3.13 wheels may lag; prefer 3.11/3.12.
- **`torch` download is large/slow.** The CPU build is pulled automatically; it
  is several hundred MB. A GPU is **not** required — the BGE reranker runs on CPU.
- **Long-path errors** when the model cache is created. Enable long paths:
  `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force` (admin), then reboot.
- **Hugging Face cache location.** Models download to
  `%USERPROFILE%\.cache\huggingface`. Set `$env:HF_HOME` before running to
  relocate it to a drive with space.

## Usage

### Run the full experiment suite (builds indexes + report)

```bash
python run_experiments.py                 # experiments A, B, C, D + RAGAS
python run_experiments.py --no-ragas      # skip the slower RAGAS stage
python run_experiments.py --skip-build    # reuse existing FAISS indexes
```

This writes:
- `reports/comparison_report.md` — populated tables + findings prompts
- `reports/results.json` — raw metric values

### Launch the Streamlit app

```bash
streamlit run src/app.py
```

In the app you can: upload documents or index the bundled samples, pick the
chunking method, toggle reranking, ask questions (answer + retrieved chunks with
scores and metadata), and use **Comparison mode** to view Fixed vs Semantic
answers side-by-side.

### Evaluation notebook

`notebooks/evaluation.ipynb` walks through ingestion → chunking → retrieval →
reranking → metrics interactively and renders the comparison charts.

## The four experiments

| Experiment | Chunking | Reranking |
|---|---|---|
| A | Fixed | No |
| B | Fixed | Yes |
| C | Semantic | No |
| D | Semantic | Yes |

## Configuration

All knobs live in [`src/config.py`](src/config.py) and can be overridden via
`.env`:

| Setting | Default |
|---|---|
| Embedding model | `text-embedding-3-large` (alt: `text-embedding-3-small`) |
| LLM | `gpt-4o-mini` |
| Reranker | `BAAI/bge-reranker-large` |
| `chunk_size` / `chunk_overlap` | `500` / `50` |
| Retrieval `top_k` / rerank `top_n` | `10` / `5` |

## Notes & limitations

- Sample documents are **synthetic** and for demonstration only.
- Retrieval relevance is judged at the document level against
  `eval/questions.json`; for finer-grained eval, label relevant chunk ids.
- RAGAS makes additional LLM calls and will consume OpenAI tokens.
