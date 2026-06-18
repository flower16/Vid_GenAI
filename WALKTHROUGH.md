# SolarBillIQ — User Walkthrough

A step-by-step guide to running a plan comparison. Each step has a text mockup of
the screen plus a placeholder where you can drop your own screenshot.

> To add real screenshots: take a screenshot of each screen, save it under
> `docs/img/` (e.g. `docs/img/01-login.png`), and the `![...]` lines below will
> render it.

Prerequisites: backend running on `http://localhost:8000`, frontend on
`http://localhost:5173` (see [README.md](README.md) → Quickstart).

---

## Step 1 — Register / Sign in

Open **http://localhost:5173**.

```
┌───────────────────────────────────────────┐
│  SolarBillIQ                                │
│  Create an account.                         │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │ email                               │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │ password                            │   │
│  └─────────────────────────────────────┘   │
│  [ Register ]                               │
│                                             │
│  Have an account? Sign in                   │
└───────────────────────────────────────────┘
```

![Login screen](docs/img/01-login.png)

Enter any email + password and click **Register** (or toggle to **Sign in** if you
already have an account).

---

## Step 2 — Enter usage & (optionally) upload data

```
                                                        Sign out ↗
SolarBillIQ — Frisco / Oncor Plan Comparison      ┌── Past comparisons ──┐
                                                   │ (empty until you run)│
Usage kWh/mo [1100]  Export kWh/mo [600]           │                      │
Self-consumed [350]  ☐ Battery   ☐ EV              ├── Uploaded files ────┤
                                                   │ (none yet)           │
┌ Solar production CSV ┐ ┌ Smart Meter TX ┐ ┌ Bill PDF ┐
│ [Choose file]        │ │ [Choose file]  │ │ [Choose] │
└──────────────────────┘ └────────────────┘ └──────────┘
                                                   └──────────────────────┘
        [ Compare plans ]
```

![Intake screen](docs/img/02-intake.png)

- The default numbers (1100 / 600 / 350) work out of the box.
- **Optional uploads:** `data/samples/solar_production.csv` (solar box) and
  `data/samples/smt_usage.csv` (SMT box). Uploaded data overrides the typed numbers.
- **The Bill PDF is optional** — it only auto-fills your *current* plan rates for the
  savings-vs-current column. Skip it for a first run.

---

## Step 3 — Upload preview (only if you uploaded a CSV)

Each upload box confirms the file and shows what was parsed:

```
┌ Solar production CSV ──────────────┐
│ [Choose file]  ✓ solar_...csv      │
│ { "monthly_production_kwh": 936,   │
│   "monthly_export_kwh": 587,       │
│   "monthly_self_consume_kwh": 349 }│
└────────────────────────────────────┘
```

![Upload preview](docs/img/03-upload-preview.png)

This is the deterministic parser reading your file — confirm the numbers look right
before comparing.

---

## Step 4 — Click "Compare plans" and read the results

**Strategy cards** (best plan per situation):

```
┌ BEST OVERALL ─┐ ┌ BEST WITHOUT ─┐ ┌ BEST FOR EV ─┐
│ TXU Energy    │ │   BATTERY     │ │  (REP)       │
│ Solar Buyback │ │ TXU Energy    │ │ Free Nights  │
│ $887/yr       │ │ $887/yr       │ │ $1,4xx/yr    │
└───────────────┘ └───────────────┘ └──────────────┘
```

**Comparison table** (ranked by lowest annual cost; #1 row highlighted green):

```
# │ Provider     │ Plan Type     │ Energy │ Buyback │ TDU    │ Base │ Monthly │ Annual │ Savings
──┼──────────────┼───────────────┼────────┼─────────┼────────┼──────┼─────────┼────────┼────────
1 │ TXU Energy   │ solar_buyback │ $123.90│ -$96.84 │ $31.26 │ 9.95 │ $73.90  │ $886.80│  ...
2 │ Ambit Energy │ solar_buyback │  ...   │  ...    │ $31.26 │ ...  │  ...    │  ...   │  ...
3 │ Gexa Energy  │ solar_buyback │  ...   │ -$18.30 │ $31.26 │ 0.00 │  ...    │  ...   │  ...
… (6 rows)
```

**Explanation** (below the table):

> *Lowest annual cost: TXU Energy TXU Solar Buyback 12 at $886.8/yr. Buyback offsets
> energy charges only; Oncor TDU delivery is not reduced.*

![Results](docs/img/04-results.png)

**The key thing to notice:** the **TDU column stays $31.26 across every plan** — a solar
buyback credit reduces the *energy* charge only, never Oncor's delivery charge. That's
the rule that keeps this comparison honest.

---

## Step 5 — History

The right sidebar now lists your run and your uploads. Click a past run to re-open it
(results are stored durably, so they survive a server restart):

```
┌── Past comparisons ──────┐
│ TXU Energy — $887/yr     │  ← click to re-open
│ TXU Solar Buyback 12 ·   │
│ 6/17/2026, 4:54 PM       │
├── Uploaded files ────────┤
│ [solar] solar_...csv · ok│
│ [smt]   smt_...csv  · ok │
└──────────────────────────┘
```

![History panel](docs/img/05-history.png)

---

## Where the data lives

Everything is in **`backend/solarbilliq.db`** (SQLite):

| Table | Holds |
|---|---|
| `jobs` | each run + full result JSON |
| `bill_calculations` | one row per ranked plan (the table above) |
| `audit_logs` | citations + run summary |
| `uploaded_files` | upload metadata (kind, name, hash, parse status) |
| `electricity_plans` / `tdu_charges` | seeded Oncor catalog |
| `users` | accounts |

Raw uploaded files sit in `backend/uploads/` (named by content hash).

---

## Optional: enable the AI-written explanation

By default the explanation is a deterministic one-liner. To get the
Claude Opus 4.8 narrative, put a real key in `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

and run another comparison. A missing or invalid key safely falls back to the
one-liner — it never breaks the ranking.

---

## Using the MCP server (optional, advanced)

The same calculation/lookup/parsing capabilities are exposed as an MCP server, so
**Claude Desktop** can call them directly — no web UI involved.

**1. Run it standalone** to confirm it starts:
```powershell
cd "f:\GenAI Week3 Project\backend"
python -m app.mcp.server
```
(It waits on stdio — Ctrl+C to stop. No output is normal.)

**2. Register in Claude Desktop.** Merge the contents of
`backend\app\mcp\claude_desktop_config.example.json` into your config at
`%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude Desktop. The
`solarbilliq` tools appear in the 🔌 menu.

**3. Ask Claude** (it picks the tools):
> "Use plan_lookup, then rank these plans for an 8 kW Oncor home using 750 kWh
> import and 600 kWh export. Remember TDU isn't offset by buyback."

Tools available: `calc_bill`, `calc_annual`, `rank`, `tdu_lookup`, `plan_lookup`,
`parse_solar`, `parse_smt`, `parse_bill`, `efl_search`.

## Multi-agent coordinator (optional, advanced)

`backend/app/agent/router.py` routes a request by domain:

```
route("compare my solar plans")   → energy domain  → local LangGraph run ✅
route("analyze this 10-K")        → finance domain  → external MCP server
route("summarize patient claims") → healthcare      → external MCP server
```

The **energy** domain works out of the box. **Finance** and **healthcare** connect to
sibling projects' MCP servers once you set their launch commands in `backend\.env`:
```
FINANCE_MCP_COMMAND=python -m finance_rag.mcp.server
HEALTHCARE_MCP_COMMAND=python -m healthcare.mcp.server
```
Until then they return `not_connected` with instructions — no fake integration.

---

## Troubleshooting (issues you may hit, and fixes)

| Symptom | Cause | Fix |
|---|---|---|
| Login/register → **"Network Error"** | Backend not running on :8000 | Start it: `cd backend; uvicorn app.main:app --reload`. Both terminals must be alive. |
| `/auth/login` → **401** | That account was never created (or wrong password) | Click **Register** (not Sign in) to create it first. |
| Table shows only the **header, no rows** | The compare run errored | Check the latest job: `python -c "import sqlite3;c=sqlite3.connect('solarbilliq.db');print(c.execute('select status from jobs order by id desc limit 1').fetchone())"`. Common cause: a bad `ANTHROPIC_API_KEY` — leave it blank to use the fallback. |
| Compare/upload stuck on **"Comparing…/uploading…"** | Backend down or unreachable | Confirm `curl http://localhost:8000/health` returns `{"status":"ok"}`. |
| Vite starts on **5174** instead of 5173 | An old `npm run dev` still holds 5173 | Open the URL Vite actually prints, or free 5173: `Get-NetTCPConnection -LocalPort 5173` → `Stop-Process -Id <PID> -Force`. CORS now allows any localhost port. |
| Multi-agent finance/healthcare → **"not_connected"** | `FINANCE_MCP_COMMAND` / `HEALTHCARE_MCP_COMMAND` empty in `backend\.env` | Set them (see README → Multi-agent), then **restart the backend** (`.env` changes don't auto-reload). |
| Multi-agent → **"did not respond within 90s"** | Heavy ML imports were slow inside the MCP async context | Already fixed via `_prewarm()` at server startup in each project's `mcp_server.py`. |
| `.env` keys reverted to `your-...` placeholders | `Copy-Item .env.example .env` was re-run | **Only copy once.** After that, edit `.env` directly — never copy over it again. |
| bcrypt `__about__` AttributeError on register | bcrypt ≥ 4.1 vs passlib 1.7 | `pip install "bcrypt<4.1"` (already pinned in requirements). |

**The golden rule:** you need **two terminals running at once** — `uvicorn` (backend, :8000) and
`npm run dev` (frontend, :5173). Most "not working" reports are one of them not running.

---

## Appendix — Original Project Brief

The prompt that kicked off this project, preserved verbatim:

> Act as a senior AI architect, energy analyst, and full-stack engineer.
>
> I want to build an AI assistant that compares the lowest total electricity bill
> strategy for my solar production pattern in Frisco, Texas, Oncor territory.
>
> **Use this tech stack:**
> - React frontend
> - FastAPI backend
> - LangGraph agent workflow
> - LangChain tools and orchestration
> - MCP tool integrations
> - RAG architecture
> - SQLite for structured app data
> - Pinecone vector database
> - LlamaIndex for document ingestion and retrieval
> - Electricity bill PDF parser
> - Smart Meter Texas data ingestion
> - Solar production data ingestion
>
> **Business Goal:** Build an AI assistant that helps a Texas solar homeowner
> compare electricity plans and find the lowest total annual electricity cost.
>
> **Location:** City: Frisco, Texas · Utility Territory: Oncor
>
> **Plans to Compare:** TXU Solar Buyback · Gexa Solar Buyback · Ambit Solar
> Buyback · Free Nights plans · Battery + Free Nights strategy · VPP / battery
> participation plans · Any better Oncor-area solar plans currently available
>
> **User Inputs:** Solar system size (kW) · Battery installed (Y/N) · Battery
> capacity (kWh) · EV ownership (Y/N) · Average monthly usage (kWh) · Average
> monthly solar production (kWh) · Monthly solar exported to grid (kWh) · Monthly
> solar self-consumed (kWh) · Current provider · Current energy rate · Current TDU
> charges · Current base charge · Current buyback rate
>
> **Required Architecture:**
> 1. React frontend for uploading bills, entering solar data, and viewing plan comparisons.
> 2. FastAPI backend for APIs, authentication, file processing, and AI workflow execution.
> 3. SQLite database for users, uploaded files, plan metadata, calculations, and audit logs.
> 4. Pinecone for storing embedded EFL documents, provider terms, buyback rules, and TDU documents.
> 5. LlamaIndex for document ingestion, chunking, metadata tagging, and retrieval.
> 6. LangChain for tools, agents, calculators, and plan comparison logic.
> 7. LangGraph for multi-step workflow orchestration.
> 8. MCP servers/tools for: Smart Meter Texas usage data · solar production files ·
>    bill PDF parsing · EFL/rate document parsing · electricity plan lookup · TDU
>    charge lookup · calculation engine.
>
> **Required AI Workflow** — a LangGraph workflow with nodes for:
> 1. User data collection 2. Bill upload parsing 3. Smart Meter Texas data ingestion
> 4. Solar production ingestion 5. Electricity plan retrieval 6. EFL document RAG
> retrieval 7. TDU charge extraction 8. Monthly bill calculation 9. Annual bill
> calculation 10. Plan ranking 11. Explanation generation 12. Recommendation output
>
> **Required Calculations:** Imported grid energy cost · Solar self-consumption value
> · Exported solar buyback credit · Oncor TDU delivery charges · Monthly base fees ·
> Taxes and miscellaneous fees · Estimated monthly bill · Estimated annual bill ·
> Savings compared to current plan · Best strategy with battery · Best strategy
> without battery · Best strategy for EV owner
>
> **Important Rules:**
> - Do not assume TDU charges are offset unless the plan explicitly says so.
> - Treat "1:1 buyback" as energy-charge-only unless documents prove otherwise.
> - Clearly separate energy charges from TDU delivery charges.
> - Use actual user data when uploaded.
> - If data is missing, state assumptions clearly.
> - Rank plans by lowest total annual cost.
>
> **Required Output:** Complete system architecture · React frontend component
> structure · FastAPI endpoint design · SQLite schema · Pinecone index design ·
> LlamaIndex ingestion pipeline · LangGraph workflow design · LangChain tool design ·
> MCP server/tool design · RAG retrieval strategy · Security architecture ·
> Deployment architecture · Implementation roadmap · Example code skeletons (FastAPI
> app, React UI, SQLite models, Pinecone setup, LlamaIndex ingestion, LangGraph
> workflow, LangChain tools, MCP tool interface, bill calculation engine).
>
> **Final Output Format:** Clear sections, text architecture diagrams, tables, sample
> code, a comparison table (Provider | Plan Type | Energy Cost | Buyback Credit | TDU
> Charges | Base Fees | Estimated Monthly Bill | Estimated Annual Bill | Best For),
> ending with a recommended MVP build plan.

The full architecture response to this brief is in [ARCHITECTURE.md](ARCHITECTURE.md);
the running implementation is described in [README.md](README.md).

### Sibling project prompts (reached via the multi-agent coordinator)

The coordinator routes finance/healthcare questions to two earlier projects. Their
original prompts are preserved here so the whole multi-agent system is documented in
one place.

**Financial RAG** (`F:\GenAI-Week2-Vid\financial-rag`) — routed as the **finance** domain:

> Build a RAG pipeline that answers questions across financial documents — SEC
> filings, earnings call transcripts, insurance claims, or loan documents. Implement
> two chunking strategies (fixed-size vs. semantic chunking) and compare retrieval
> quality on the same set of queries. Add a reranking step and measure the
> improvement. … Deliverable: a working financial RAG pipeline with a chunking
> strategy comparison report and reranking impact analysis.
>
> *(Claude build prompt:)* Build the complete project from this specification.
> Generate production-quality Python code, folder structure, README,
> requirements.txt, Streamlit app, evaluation scripts, sample datasets, and
> comparison report template. Provide files one by one in separate code blocks.

**Hospital Readmission Risk Analytics** (`F:\Healthcare_data_analytics_2`) — routed as the **healthcare** domain:

> Act as an expert healthcare data scientist and full-stack Python developer. I want
> to build a Streamlit web application that analyzes hospital readmission trends to
> identify high-risk patient cohorts. Generate the complete Python code for an app
> that does: (1) synthetic data generation — 10,000 patient discharges with
> Patient_ID, Age, Length_of_Stay, Admission_Type, Number_of_Comorbidities,
> Discharge_Department, Readmitted_30_Days; (2) EDA with Plotly — readmission rates
> by admission type & department, correlation matrix; (3) an interpretable ML model
> (Logistic Regression / Random Forest) to predict 30-day readmission; (4) a feature
> importance chart; (5) an interactive "What-If" sidebar for live risk. Include
> clean, well-commented code and run instructions.

Each of these projects was wrapped with a small MCP server (`mcp_server.py` at its
root) so this coordinator can call it — see [README.md](README.md) → Multi-agent.
