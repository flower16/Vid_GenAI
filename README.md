# SolarBillIQ

An AI assistant that compares Texas electricity plans for a **rooftop-solar home in Frisco, TX (Oncor TDU territory)** and ranks them by **lowest total annual cost** — using the homeowner's real usage, solar export/self-consumption, and the actual terms in each plan's EFL.

> **The core rule:** a buyback / "1:1" credit offsets the **energy charge only**. Oncor's TDU delivery charge (~$4.23/mo + ~3.6¢/kWh) is paid on every imported kWh regardless, unless a plan's EFL explicitly proves otherwise. The engine never assumes TDU offset — that's what keeps the comparison honest.

Full design: see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Quickstart (Docker — one command)

```bash
docker compose up --build
```

- Frontend → http://localhost:5173
- Backend / Swagger docs → http://localhost:8000/docs

The backend seeds the Oncor plan catalog on boot. **Register an account** in the UI and run a comparison. Data (users, runs, uploads) persists in a named volume across restarts.

API keys are **optional** — without them, compare/rank/table fully work; the LLM explanation falls back to a deterministic string and RAG is disabled. To enable them, create `backend/.env` (copy `backend/.env.example`) and re-run.

> Needs Docker Compose **v2.24+** (for the optional `env_file`). On older versions, create `backend/.env` and simplify that block in [docker-compose.yml](docker-compose.yml).

---

## Quickstart (manual / local dev)

**Backend**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # optional: add keys
python seed_plans.py          # creates solarbilliq.db + loads plans
uvicorn app.main:app --reload # http://localhost:8000
```

**Frontend** (second terminal)
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

---

## What it does (end to end)

```
Register/login → enter usage  ┐
upload solar/SMT CSV + bill PDF ┘→ POST /compare → LangGraph (12 nodes)
   → parse files → retrieve Oncor plans → EFL RAG extract (cited)
   → Oncor TDU lookup → monthly calc → annual calc → rank
   → Claude Opus 4.8 explanation (grounded) → ranked table + best-for cards
```

The LLM never does arithmetic — a deterministic engine computes every dollar; the model only extracts cited parameters and narrates the result.

## Tech stack

React (Vite) · FastAPI · LangGraph · LangChain · **MCP server (FastMCP)** · RAG (LlamaIndex + Pinecone) · SQLite · Claude Opus 4.8 · JWT auth.

---

## MCP server

The engine, lookups, parsers, and RAG are exposed as Model Context Protocol tools in
[backend/app/mcp/server.py](backend/app/mcp/server.py), so any MCP client (Claude
Desktop, the coordinator agent) can call them directly.

```bash
cd backend
python -m app.mcp.server          # stdio transport
```

Tools: `calc_bill`, `calc_annual`, `rank`, `tdu_lookup`, `plan_lookup`,
`parse_solar`, `parse_smt`, `parse_bill`, `efl_search`.

**Register in Claude Desktop** — merge [claude_desktop_config.example.json](backend/app/mcp/claude_desktop_config.example.json)
into your `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\…`), then ask
Claude things like *"use plan_lookup then rank these for an 8 kW no-battery Oncor home."*

## Multi-agent coordinator (cross-project)

[backend/app/agent/router.py](backend/app/agent/router.py) routes a request by domain:
**energy** runs this project's LangGraph workflow locally; **finance** and
**healthcare** are MCP clients to two sibling projects (a Financial-RAG project, a
Healthcare-analytics project), each exposing its own root-level `mcp_server.py`. In the
UI, the **"Ask anything"** box (top of the results page) sends free-text to
`POST /agent/route`, shows a color-coded domain badge, and renders the answer.

```
route("compare my solar plans")     → energy     → local LangGraph comparison
route("what was ACME revenue …10-K") → finance    → financial-rag MCP server
route("readmission rates by dept")  → healthcare → healthcare MCP server
```

### Detailed setup (to make finance/healthcare answer)

1. **Install `mcp` in all three environments:**
   ```powershell
   # this project's backend
   cd backend; pip install mcp
   # financial-rag (its own venv)
   & "F:\GenAI-Week2-Vid\financial-rag\.venv\Scripts\pip.exe" install mcp
   # healthcare (base env)
   pip install mcp
   ```
2. **Set the launch commands in `backend\.env`** (forward slashes, no spaces; point at
   each project's own interpreter if it has a venv):
   ```
   FINANCE_MCP_COMMAND=F:/GenAI-Week2-Vid/financial-rag/.venv/Scripts/python.exe F:/GenAI-Week2-Vid/financial-rag/mcp_server.py
   HEALTHCARE_MCP_COMMAND=python F:/Healthcare_data_analytics_2/mcp_server.py
   ```
3. **Finance needs an OpenAI key in *its own* `.env`** (`F:\GenAI-Week2-Vid\financial-rag\.env`)
   — it embeds the query + calls the LLM. Healthcare needs no keys.
4. **Restart the backend** (`.env` changes don't auto-reload), then use the Ask box.

Until the commands are set, those domains return `not_connected` (no fake
integration). Each sibling `mcp_server.py` **pre-warms its heavy imports/model at
startup** (`_prewarm()` / `_ensure_model()` before `mcp.run()`) — without this, the
first call is ~30× slower inside the MCP async context and times out.

---

## Sample data

Pre-generated, sized to an 8 kW Frisco profile (one month of daily readings):

```
data/samples/solar_production.csv   → upload as "solar"
data/samples/smt_usage.csv          → upload as "smt"
```

Bills are real artifacts you download from your provider (TXU/Gexa/…) as PDF; the parser reads standard REP bill wording. You can also skip the bill and type current-plan numbers in the form.

---

## Tests

```bash
cd backend
python -m pytest tests/ -q     # 13 tests: bill engine + file parsers
```

Covers the load-bearing rules: TDU never offset by buyback, free-nights, min-usage fees, ranking order, and the solar/SMT/bill parsers.

---

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | JWT auth |
| GET | `/me` | current user |
| POST | `/files/{bill\|solar\|smt}` | upload + parse (SHA-256 dedup) |
| GET | `/files` | list your uploads |
| POST | `/compare` | run the comparison (returns `job_id`) |
| GET | `/compare/{job_id}` | poll result |
| GET | `/compare/history` | your past runs |
| POST | `/rag/ingest` | ingest an EFL/TDU PDF into Pinecone |
| POST | `/rag/query` | grounded retrieval |
| POST | `/agent/route` | multi-agent coordinator: classify + dispatch to a domain |
| POST | `/agent/classify` | routing decision only (no dispatch) |

All data endpoints are scoped to the authenticated user.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app + routers
    config.py          env-driven settings
    auth.py            JWT + password hashing
    calc/engine.py     deterministic bill math  ← the credibility core
    agent/             LangGraph workflow, tools, Opus 4.8 explainer
    rag/               LlamaIndex ingest, Pinecone, retriever
    ingest/files.py    bill PDF + solar/SMT CSV parsers
    mcp/server.py      MCP server (FastMCP) exposing engine/lookups/parsers/RAG
    agent/router.py    multi-agent coordinator (energy local · finance/health via MCP)
    api/               auth, compare, files, ingestion routes
    models.py          SQLite schema
  seed_plans.py        Oncor plan catalog (rates ⚠ verify against EFL)
  tests/               pytest suite
frontend/
  src/                 React UI (login, intake, upload, results, history)
data/samples/          example solar + SMT CSVs
docker-compose.yml     one-command startup
ARCHITECTURE.md        full system design
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Network Error" on login | Backend not running — start `uvicorn app.main:app --reload` (need both terminals). |
| `/auth/login` → 401 | Account not created yet — **Register** first. |
| Comparison table empty (header only) | A run errored; check `jobs.status`. Usually a bad `ANTHROPIC_API_KEY` — leave it blank for the fallback. |
| Vite uses port 5174 | An old dev server holds 5173; open the printed URL (CORS allows any localhost port). |
| Finance/healthcare `not_connected` | Set `FINANCE_MCP_COMMAND`/`HEALTHCARE_MCP_COMMAND` in `.env`, then restart backend. |
| Multi-agent "did not respond within 90s" | Already handled by `_prewarm()` in each sibling `mcp_server.py`. |
| `.env` reset to placeholders | `Copy-Item .env.example .env` was re-run — only do that once; edit `.env` directly after. |
| bcrypt `__about__` error | `pip install "bcrypt<4.1"`. |

Detailed, step-by-step troubleshooting + the **original prompts for all three projects**
(solar, financial-RAG, healthcare) are in [WALKTHROUGH.md](WALKTHROUGH.md).

## Status & caveats

- Seeded plan rates are **approximate** (from 2026 public comparison sites) and must be verified against each plan's current EFL — the RAG `efl_rag_extract` node is designed to override them with cited values once you ingest real EFL PDFs.
- Texas has **no mandated net metering**; "buyback" plans are voluntary REP offers that can change.
- The default `JWT_SECRET` is a dev placeholder — set a real one in `.env` before any real deployment.
