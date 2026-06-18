# SolarBillIQ — AI Electricity Plan Optimizer for Texas Solar Homeowners

> Compares electricity plans for a rooftop-solar home in **Frisco, TX (Oncor TDU territory)** and ranks them by **lowest total annual cost**, using the homeowner's real usage, solar export/self-consumption, and the actual terms in each plan's **EFL (Electricity Facts Label)**.

This document is the master design. Runnable skeletons referenced in Section 14 live as real files in `backend/` and `frontend/`.

---

## 0. Domain primer (why this is non-trivial in Texas)

In a deregulated ERCOT market served by the **Oncor** TDU, a residential bill has two structurally different parts:

| Component | Who sets it | Offsettable by solar export? |
|---|---|---|
| **Energy charge** (¢/kWh × kWh imported) | Retail Electric Provider (REP) | Often, via buyback credit — **but only the energy portion** |
| **TDU delivery charge** (fixed $/mo + ¢/kWh delivered) | Oncor (regulated) | **Almost never** — you pay to *receive* energy regardless of net metering |
| **REP base/monthly fee** | REP | No |
| **Taxes & misc (PUC, gross receipts, sales tax)** | State/local | No |

**The core modeling rule:** a "1:1 buyback" or "net metering" plan in Texas almost always credits the **energy charge only**. Oncor's volumetric delivery charge (~3–5 ¢/kWh) and the fixed monthly delivery charge still apply to every kWh you import. A naive comparison that nets export against gross consumption will badly overstate solar savings. This system refuses to assume TDU offset unless the EFL text proves it.

---

## 0b. As-Built Status (what actually shipped)

This document is the full design. The table below maps each piece to its
implementation state so the design isn't mistaken for the build.

| Area | Status | Where |
|---|---|---|
| Deterministic bill engine | ✅ built + **13 unit tests** | `backend/app/calc/engine.py`, `backend/tests/` |
| LangGraph 12-node workflow | ✅ built | `backend/app/agent/workflow.py` |
| LangChain tools | ✅ built | `backend/app/agent/tools.py` |
| Claude Opus 4.8 explanation | ✅ built (safe fallback) | `backend/app/agent/explainer.py` |
| RAG: LlamaIndex ingest + Pinecone, SHA-256 dedup | ✅ built | `backend/app/rag/` |
| Bill PDF + solar/SMT CSV parsers | ✅ built | `backend/app/ingest/files.py` |
| File upload endpoints + persistence | ✅ built (per-user) | `backend/app/api/files.py` |
| Compare runs persisted (jobs, calcs, audit) | ✅ built | `backend/app/api/compare.py` |
| History endpoints + UI panel | ✅ built | `compare.py`, `frontend/.../history/` |
| JWT auth + per-user scoping | ✅ built | `backend/app/auth.py`, `api/auth_routes.py` |
| **MCP server (FastMCP)** | ✅ built | `backend/app/mcp/server.py` |
| **Multi-agent coordinator** | ✅ built (energy local; finance/health via external MCP) | `backend/app/agent/router.py` |
| React UI (login, intake, upload, results, history) | ✅ built | `frontend/src/` |
| Docker one-command startup | ✅ built | `docker-compose.yml`, `*/Dockerfile` |
| `/intake`, `/plans`, `/admin/efl/ingest`, `/audit` endpoints | ⚠️ designed, not built (intake rides in the `/compare` body; ingest is `POST /rag/ingest`; audit is read from SQLite) | — |
| Seasonal usage curve in annual calc | ⚠️ supported in engine, flat by default | `engine.calc_annual_bill` |

Some endpoint names in §3 below are the original design; the shipped routes are in
[README.md](README.md) → Key endpoints.

---

## 1. Complete System Architecture

```
                          ┌──────────────────────────────────────────┐
                          │              React Frontend                │
                          │  Bill upload · Solar/usage forms · Results │
                          └───────────────────┬────────────────────────┘
                                              │ HTTPS / JWT
                          ┌───────────────────▼────────────────────────┐
                          │                FastAPI Backend               │
                          │  Auth · File intake · Job orchestration ·    │
                          │  Results API · Audit logging                 │
                          └───┬───────────────┬───────────────┬─────────┘
                              │               │               │
            ┌─────────────────▼──┐   ┌────────▼────────┐   ┌──▼─────────────────┐
            │   SQLite (app DB)  │   │  LangGraph      │   │  Object/File store │
            │ users, files,      │   │  workflow       │   │ (uploads: PDF/CSV) │
            │ plans, calcs, audit│   │  orchestrator   │   └────────────────────┘
            └────────────────────┘   └───┬─────────────┘
                                         │ invokes nodes (LangChain tools)
                ┌────────────────────────┼─────────────────────────────────┐
                │                        │                                  │
        ┌───────▼────────┐      ┌────────▼─────────┐              ┌─────────▼────────┐
        │  RAG layer     │      │  Calc engine     │              │   MCP servers    │
        │ LlamaIndex     │      │ (deterministic   │              │ smt · solar ·    │
        │ ingest+retrieve│      │  bill math)      │              │ billparse · efl ·│
        │  Pinecone idx  │      └──────────────────┘              │ plans · tdu ·    │
        └───────┬────────┘                                        │ calc             │
                │ embeddings (Voyage/OpenAI)                       └──────────────────┘
        ┌───────▼────────┐
        │   Pinecone     │  EFLs, provider terms, buyback rules, Oncor TDU docs
        └────────────────┘
```

**Separation of concerns (critical):**
- **RAG (Pinecone + LlamaIndex)** answers *qualitative/contractual* questions: "Does this plan credit exports at 1:1? Does the credit apply to TDU? Is there a minimum usage fee? What are the free-night hours?"
- **Calc engine (deterministic Python)** does *all arithmetic*. LLMs never compute the bill — they extract parameters (cited to source text), the engine computes, and the LLM only explains. This makes results auditable and reproducible.
- **LangGraph** sequences the steps and handles missing-data branching.
- **MCP** wraps each external/operational capability as a typed tool so the agent (or other clients like Claude Desktop) can call them uniformly.

---

## 2. React Frontend Component Structure

```
src/
├── App.jsx                      # routing + auth gate
├── api/client.js                # axios w/ JWT interceptor
├── store/                       # Zustand: session, intake, jobStatus, results
├── pages/
│   ├── LoginPage.jsx
│   ├── DashboardPage.jsx
│   ├── IntakePage.jsx           # the user-input wizard
│   ├── UploadPage.jsx           # bill / solar / SMT file drop
│   └── ResultsPage.jsx
├── components/
│   ├── intake/
│   │   ├── SystemProfileForm.jsx   # solar kW, battery Y/N + kWh, EV Y/N
│   │   ├── UsageForm.jsx           # monthly usage, production, export, self-consume
│   │   └── CurrentPlanForm.jsx     # provider, energy rate, TDU, base, buyback
│   ├── upload/
│   │   ├── BillDropzone.jsx
│   │   └── IngestStatus.jsx        # polls job status
│   ├── results/
│   │   ├── PlanComparisonTable.jsx # the headline table (Section "Required Output")
│   │   ├── SavingsBarChart.jsx     # recharts: annual cost per plan
│   │   ├── StrategyCards.jsx       # best w/ battery · w/o battery · EV
│   │   ├── ExplanationPanel.jsx    # LLM narrative + EFL citations
│   │   └── AssumptionsBanner.jsx   # surfaces "missing data → assumed" notes
│   └── common/ (Stepper, FileChip, Toast, Spinner)
└── hooks/ (useJobPolling, useAuth)
```

Flow: **Intake → Upload → "Run comparison" (POST) → poll job → Results**. The `AssumptionsBanner` is mandatory UX — it makes the "state assumptions clearly" rule visible.

---

## 3. FastAPI Endpoint Design

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | JWT issuance |
| GET | `/me` | current user |
| POST | `/intake` | save/update user profile + usage + current plan |
| GET | `/intake` | fetch saved intake |
| POST | `/files/bill` | upload bill PDF (multipart) → stored, queued for parse |
| POST | `/files/solar` | upload solar production CSV |
| POST | `/files/smt` | upload Smart Meter Texas export CSV |
| GET | `/files` | list user's uploaded files + parse status |
| POST | `/compare` | **kick off LangGraph run** → returns `job_id` |
| GET | `/compare/{job_id}` | job status + (when done) ranked results |
| GET | `/plans` | list known plans (admin/catalog) |
| POST | `/admin/efl/ingest` | ingest an EFL/TDU doc into RAG (admin) |
| GET | `/audit/{job_id}` | full audit trail for a calculation run |

All mutating routes require JWT; admin routes require role claim. Responses use Pydantic schemas (`backend/app/schemas.py`).

---

## 4. SQLite Schema

```sql
users(id PK, email UNIQUE, password_hash, role DEFAULT 'user', created_at)

intake_profiles(
  id PK, user_id FK, solar_kw, battery_installed BOOL, battery_kwh,
  ev_owned BOOL, avg_monthly_usage_kwh, avg_monthly_production_kwh,
  monthly_export_kwh, monthly_self_consume_kwh,
  current_provider, current_energy_rate, current_tdu_charge,
  current_base_charge, current_buyback_rate, updated_at)

uploaded_files(
  id PK, user_id FK, kind ENUM('bill','solar','smt'),
  original_name, stored_path, sha256, parse_status ENUM('pending','ok','error'),
  parsed_json TEXT, error TEXT, created_at)

plans(
  id PK, provider, plan_name, plan_type,   -- 'solar_buyback','free_nights','vpp', etc.
  efl_doc_id, energy_rate_cents, base_charge_monthly,
  buyback_rate_cents, buyback_applies_to_tdu BOOL DEFAULT 0,  -- KEY flag
  free_nights_start, free_nights_end, min_usage_fee, term_months,
  source_url, efl_effective_date, raw_terms TEXT)

tdu_charges(
  id PK, tdu_name DEFAULT 'Oncor', fixed_monthly, volumetric_cents_per_kwh,
  effective_date, source_doc_id)

calculations(
  id PK, job_id, user_id FK, plan_id FK,
  imported_cost, self_consumption_value, export_credit, tdu_delivery_cost,
  base_fee, taxes_misc, est_monthly_bill, est_annual_bill,
  annual_savings_vs_current, rank, assumptions_json TEXT, created_at)

jobs(id PK, job_id UNIQUE, user_id FK, status, current_node, result_json TEXT, created_at, finished_at)

audit_logs(id PK, job_id, node, tool, input_hash, output_summary, citations_json, ts)
```

Key design choice: `plans.buyback_applies_to_tdu` defaults to **0 (false)**. It is only flipped to true when an EFL explicitly states TDU offset — enforcing the "do not assume TDU offset" rule at the data layer.

---

## 5. Pinecone Index Design

- **Index:** `solarbilliq-docs`, metric `cosine`, dim per embed model (e.g. 1024 Voyage / 1536 OpenAI), serverless.
- **Namespaces** (logical separation, cheaper than filters at scale):
  - `efl` — Electricity Facts Labels per plan
  - `terms` — Terms of Service / YRAC
  - `buyback` — solar buyback rules / surplus credit policies
  - `tdu` — Oncor delivery tariff sheets
- **Metadata per vector:** `{provider, plan_name, plan_type, doc_id, efl_effective_date, section, source_url, page, chunk_id, tdu_territory:'Oncor'}`
- **Retrieval filtering:** always filter `tdu_territory='Oncor'`; for plan-specific extraction filter by `doc_id`/`plan_name` so the RAG answer for "does buyback cover TDU?" is grounded in *that plan's* EFL, never bleeding across providers.

---

## 6. LlamaIndex Ingestion Pipeline

```
PDF/HTML EFL ─► LlamaParse / PyMuPDF ─► SentenceSplitter (512 tok, 64 overlap)
   ─► metadata tagger (provider, plan_type, effective_date, section heading,
                       contains_buyback_clause?, contains_tdu_clause?)
   ─► embed (Voyage/OpenAI) ─► upsert to Pinecone namespace
   ─► register plan/tdu row in SQLite (plans / tdu_charges)
```

Tagging step runs a small extraction prompt over each chunk to set boolean metadata (`mentions_tdu_offset`, `mentions_free_nights`) so retrieval can be precise. See `backend/app/rag/ingest.py`.

---

## 7. LangGraph Workflow Design

State object (`backend/app/agent/state.py`) carries `intake`, `parsed_files`, `candidate_plans`, `plan_params` (extracted+cited), `tdu`, `per_plan_calcs`, `ranking`, `explanation`, `assumptions[]`.

```
        ┌──────────────────────┐
START ─►│ 1 collect_user_data  │  (load intake from SQLite; flag missing fields)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 2 parse_bills        │──┐
        └─────────┬────────────┘  │ (these 3 ingestion nodes run as a fan-out;
        ┌─────────▼────────────┐  │  merge before retrieval)
        │ 3 ingest_smt         │──┤
        └─────────┬────────────┘  │
        ┌─────────▼────────────┐  │
        │ 4 ingest_solar       │──┘
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 5 retrieve_plans     │  (candidate plans for Oncor: TXU/Gexa/Ambit/free-night/VPP)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 6 efl_rag_extract    │  (per plan: buyback rate, TDU-offset?, free-night hrs,
        └─────────┬────────────┘   min-usage fee — each with citation)
                  ▼
        ┌──────────────────────┐
        │ 7 extract_tdu        │  (Oncor fixed + volumetric from tdu namespace)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 8 monthly_calc       │  (deterministic engine, per plan)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 9 annual_calc        │  (×12 w/ seasonal solar profile if available)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 10 rank_plans        │  (sort by annual total; tag best-with-battery /
        └─────────┬────────────┘   best-without / best-for-EV)
                  ▼
        ┌──────────────────────┐
        │ 11 explain           │  (LLM narrative grounded ONLY in calc outputs + citations)
        └─────────┬────────────┘
                  ▼
        ┌──────────────────────┐
        │ 12 recommend         │──► END  (writes calculations + audit rows)
        └──────────────────────┘
```

**Conditional edges:** after node 1, if required usage/solar fields are missing *and* no uploaded files cover them, the graph still proceeds but `assumptions[]` records each substituted default; `explain` and the UI banner surface them. See `backend/app/agent/workflow.py`.

---

## 8. LangChain Tool Design

Tools are thin LangChain `StructuredTool`s wrapping deterministic functions / MCP clients (`backend/app/agent/tools.py`):

| Tool | Input | Output |
|---|---|---|
| `parse_bill_pdf` | file_id | `{provider, energy_rate, tdu, base, buyback, kwh, month}` |
| `load_smt_usage` | file_id | hourly/monthly import/export series |
| `load_solar_production` | file_id | monthly production/export/self-consume |
| `retrieve_oncor_plans` | filters | candidate plan list |
| `efl_lookup` | plan_id, question | grounded answer + citation (RAG) |
| `tdu_charge_lookup` | tdu='Oncor', date | fixed + volumetric |
| `calc_monthly_bill` | plan_params + usage | full cost breakdown |
| `rank_plans` | list of annual calcs | ranked list + strategy tags |

The agent's job is **orchestration and parameter extraction**, not math. `calc_*` tools are pure functions.

---

## 9. MCP Server / Tool Design

Each capability is exposed via MCP (FastMCP) so the same tools serve both the LangGraph agent and external MCP clients (e.g. Claude Desktop). **Implemented:** `backend/app/mcp/server.py` (run with `python -m app.mcp.server`; register via `backend/app/mcp/claude_desktop_config.example.json`). Tools wrap the existing engine/lookups/parsers/RAG — no logic duplication.

| MCP tool | Wraps |
|---|---|
| `calc_bill` / `calc_annual` / `rank` | the deterministic bill engine |
| `tdu_lookup` | Oncor delivery charges (SQLite, default fallback) |
| `plan_lookup` | the `electricity_plans` catalog |
| `parse_solar` / `parse_smt` / `parse_bill` | the file parsers |
| `efl_search` | RAG retrieval (graceful if keys unset) |

Transport: stdio for local/desktop. The same FastMCP server can be served over streamable-HTTP for network clients.

### 9a. Multi-agent coordinator (cross-project)

`backend/app/agent/router.py` is a coordinator that routes a request to a **domain agent**:

```
            ┌─────────────── route(request) ───────────────┐
            │  classify_domain → energy | finance | health │
            └───┬───────────────┬───────────────┬──────────┘
                ▼               ▼               ▼
        energy (LOCAL)   finance (MCP)   healthcare (MCP)
        LangGraph run    external proj   external proj
                         MCP server      MCP server
```

The energy domain runs this project's LangGraph workflow locally. Finance and healthcare are **MCP clients** to sibling projects (Financial-RAG, Healthcare-analytics) — each exposes its own FastMCP server (`mcp_server.py` at its project root), launched via `FINANCE_MCP_COMMAND` / `HEALTHCARE_MCP_COMMAND`. Until those are configured, the coordinator returns a `not_connected` status with enablement instructions — no fabricated integration. This is the seam that lets independent projects compose without coupling their code. Reachable over HTTP via `POST /agent/route` (and `/agent/classify`); the React "Ask anything" box uses it.

**Implementation lessons baked in (Windows + stdio):**
- The MCP client runs in a **dedicated thread with a `ProactorEventLoop`** — a worker-thread `SelectorEventLoop` on Windows can't spawn subprocesses, which silently hangs the call. ([`_run_mcp_call`](backend/app/agent/router.py))
- A **90s timeout** wraps each external call so a missing/broken sibling fails fast instead of hanging the caller.
- Each sibling server **pre-warms its heavy imports/model at startup** (`_prewarm()` / `_ensure_model()` before `mcp.run()`). The same import is ~30× slower lazily inside FastMCP's async tool context (~60s) than at plain module load (~2s) — pre-warming keeps tool calls in the single-digit-seconds range.
- MCP servers must write **nothing but protocol to stdout**; debug logging goes to a file/stderr, not stdout, or it corrupts the JSON-RPC stream.
- Sibling MCP files live at the **project root named `mcp_server.py`**, *not* a folder named `mcp/` — that would shadow the `mcp` SDK package.

---

## 10. RAG Retrieval Strategy

1. **Scope hard-filter** every query: `tdu_territory='Oncor'` + target `namespace`.
2. **Plan-grounded extraction:** for each candidate plan, run targeted questions filtered to that plan's `doc_id`:
   - "What is the surplus/export credit rate and unit?"
   - "Does the credit apply to TDU/delivery charges, or energy only?" → sets `buyback_applies_to_tdu`
   - "Free-night window and hours?" / "Minimum usage fee or bill credit thresholds?"
3. **Citation-required:** the extractor must return the source chunk text + page; if no supporting chunk, the parameter is marked `unknown` and a conservative assumption is logged (TDU **not** offset, buyback = energy-only).
4. **Hybrid:** dense (Pinecone) + keyword rerank on clause terms ("delivery", "TDU", "buyback", "surplus", "1:1") to avoid missing legalese.
5. **Recency:** prefer chunks with latest `efl_effective_date`.

---

## 11. Security Architecture

- **AuthN/Z:** JWT (short-lived access + refresh), bcrypt/argon2 password hashing, role claim for admin ingestion routes.
- **File safety:** validate MIME + magic bytes, size cap, virus/structure scan, store outside web root, randomized names, SHA-256 dedupe; parse in a sandboxed worker (PDF parsers are a common RCE/zip-bomb vector).
- **PII:** SMT interval data + bills are sensitive. Encrypt at rest (SQLCipher or disk encryption), TLS in transit, per-user row scoping on every query, configurable retention/delete.
- **Secrets:** API keys (Pinecone, embeddings, LLM) via env/secret manager, never in repo.
- **LLM safety:** the LLM cannot perform math or write to DB; tools validate inputs with Pydantic; prompt-injection from EFL/bill text is contained because extracted text only flows into structured extraction, never into a tool-executing instruction channel.
- **Audit:** every node/tool call logged with input hash + citation set (`audit_logs`), enabling reproducible bill math.

---

## 12. Deployment Architecture

- **MVP:** single VM/container. `frontend` (static, Nginx/Vercel) + `backend` (Uvicorn/Gunicorn) + SQLite file + Pinecone (managed) + managed embedding/LLM API. MCP servers run in-process / as sidecars.
- **Jobs:** LangGraph runs in a background worker (FastAPI BackgroundTasks for MVP → Celery/RQ + Redis when concurrency grows).
- **Scale path:** SQLite → Postgres; uploads → S3/GCS; worker pool; OpenTelemetry tracing; LangSmith for agent observability.
- **CI/CD:** GitHub Actions → build/test → container registry → deploy; `.env`-driven config (`backend/app/config.py`).

---

## 13. Implementation Roadmap

| Phase | Deliverable |
|---|---|
| **P0 (week 1)** | Repo scaffold, SQLite models, auth, intake CRUD, calc engine + unit tests (the math is the heart — build & test first) |
| **P1** | Bill PDF parser + solar/SMT CSV ingestion; file storage |
| **P2** | RAG: LlamaIndex ingest + Pinecone; seed 5–8 Oncor EFLs + Oncor TDU sheet |
| **P3** | LangGraph workflow wiring nodes 1–12; LangChain tools |
| **P4** | MCP servers; React intake + upload + results table/charts |
| **P5** | Hardening: security, audit trail, assumptions UX, deploy |

---

## Required Output — Plan Comparison Table (example, illustrative numbers)

Assumes: 8 kW solar, **no battery**, 1,100 kWh/mo usage, 950 kWh/mo production, 600 kWh exported, 350 kWh self-consumed, Oncor TDU ≈ $4.23/mo fixed + 3.6¢/kWh. **TDU not offset** by any buyback below.

| Provider | Plan Type | Energy Cost | Buyback Credit | TDU Charges | Base Fees | Est. Monthly Bill | Est. Annual Bill | Best For |
|---|---|---|---|---|---|---|---|---|
| TXU | Solar Buyback | $115.50 | −$72.00 | $43.83 | $9.95 | **$108.6** | **$1,303** | Balanced exporters |
| Gexa | Solar Buyback | $108.90 | −$60.00 | $43.83 | $0.00 | **$104.0** | **$1,248** | No base fee, mid export |
| Ambit | Solar Buyback | $121.00 | −$78.00 | $43.83 | $4.95 | **$103.0** | **$1,236** | High exporters |
| (REP) | Free Nights | $93.50 | $0.00 | $43.83 | $9.95 | **$118.6** | **$1,423** | Night/EV charging |
| (REP) | Battery + Free Nights | $61.00 | $0.00 | $43.83 | $9.95 | **$95.8** | **$1,150** | Battery + EV owners |
| (REP) | VPP / Battery participation | $61.00 | −$15.00 (event $) | $43.83 | $9.95 | **$80.8** | **$970** | Battery owners (grid events) |

> Numbers are placeholders to demonstrate the engine's output shape. Real values come from the calc engine using parsed EFL params + the user's actual usage. Note buyback credits **never** reduce the $43.83 TDU line.

---

## Recommended MVP Build Plan

Build the **deterministic calc engine first** (`backend/app/calc/engine.py`) with thorough unit tests, because every downstream feature depends on it being correct and the whole product's credibility rests on *not* over-counting solar savings against TDU charges. Then:

1. **Engine + tests** (no UI, no LLM) — prove the math on 3 hand-worked example bills.
2. **Intake API + SQLite** — capture the 13 user inputs; manual plan params seeded by hand.
3. **One real EFL through RAG** — ingest a single TXU Solar Buyback EFL, extract buyback rate + TDU-offset flag with citation.
4. **LangGraph happy path** — nodes 1,5,6,7,8,9,10,12 end-to-end for 2–3 plans.
5. **React results table** — render the comparison table + assumptions banner.
6. **Then** add bill PDF parsing, SMT/solar ingestion, MCP, charts, auth hardening.

Ship the smallest thing that can correctly say *"For your 8 kW no-battery profile in Oncor territory, Ambit Solar Buyback is ~$1,236/yr vs your current ~$1,400 — saving ~$164, and note no plan offsets your $526/yr Oncor delivery charges."*
