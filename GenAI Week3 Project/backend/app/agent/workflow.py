"""LangGraph 12-node workflow for plan comparison.

Nodes:
 1 collect_user_data   5 retrieve_plans      9 annual_calc
 2 parse_bills         6 efl_rag_extract    10 rank_plans
 3 ingest_smt          7 extract_tdu        11 explain
 4 ingest_solar        8 monthly_calc       12 recommend

LLMs only extract params (cited) and explain. The calc engine does all math.
"""
from __future__ import annotations

import json

from langgraph.graph import StateGraph, START, END

from app.agent.state import GraphState
from app.agent.tools import _efl_lookup, _tdu_lookup
from app.calc.engine import (
    PlanParams, UsageProfile, calc_monthly_bill, calc_annual_bill, rank_plans,
)

REQUIRED_FIELDS = [
    "avg_monthly_usage_kwh", "monthly_export_kwh", "monthly_self_consume_kwh",
]


# --------------------------------------------------------------------------- #
# Node implementations
# --------------------------------------------------------------------------- #
def collect_user_data(state: GraphState) -> dict:
    intake = state.get("intake", {})
    missing = [f for f in REQUIRED_FIELDS if not intake.get(f)]
    assumptions = []
    if missing:
        assumptions.append(
            f"Missing intake fields {missing}; defaults will be substituted and flagged."
        )
    return {"missing_fields": missing, "assumptions": assumptions}


def parse_bills(state: GraphState) -> dict:
    """Parse a bill PDF if a path was supplied; fold current-plan values into intake."""
    from app.ingest.files import parse_bill_pdf
    path = state.get("intake", {}).get("bill_path")
    if not path:
        return {"parsed_bill": state.get("parsed_bill")}
    parsed = parse_bill_pdf(path)
    intake = dict(state.get("intake", {}))
    for k_bill, k_intake in (("provider", "current_provider"),
                             ("energy_rate_cents", "current_energy_rate"),
                             ("tdu_volumetric_cents", "current_tdu_charge"),
                             ("base_charge_monthly", "current_base_charge"),
                             ("buyback_rate_cents", "current_buyback_rate")):
        if k_bill in parsed and not intake.get(k_intake):
            intake[k_intake] = parsed[k_bill]
    return {"parsed_bill": parsed, "intake": intake,
            "assumptions": parsed.get("assumptions", [])}


def ingest_smt(state: GraphState) -> dict:
    """Load Smart Meter Texas usage if a path was supplied; override import/export."""
    from app.ingest.files import load_smt_csv
    path = state.get("intake", {}).get("smt_path")
    if not path:
        return {"smt_usage": state.get("smt_usage")}
    smt = load_smt_csv(path)
    intake = dict(state.get("intake", {}))
    if smt.get("monthly_import_kwh"):
        intake["monthly_import_kwh"] = smt["monthly_import_kwh"]
    if smt.get("monthly_export_kwh"):
        intake["monthly_export_kwh"] = smt["monthly_export_kwh"]
    return {"smt_usage": smt, "intake": intake,
            "assumptions": smt.get("assumptions", [])}


def ingest_solar(state: GraphState) -> dict:
    """Load solar production if a path was supplied; override production fields."""
    from app.ingest.files import load_solar_csv
    path = state.get("intake", {}).get("solar_path")
    if not path:
        return {"solar_production": state.get("solar_production")}
    solar = load_solar_csv(path)
    intake = dict(state.get("intake", {}))
    for k in ("monthly_export_kwh", "monthly_self_consume_kwh"):
        if solar.get(k):
            intake[k] = solar[k]
    if solar.get("monthly_production_kwh"):
        intake["avg_monthly_production_kwh"] = solar["monthly_production_kwh"]
    return {"solar_production": solar, "intake": intake,
            "assumptions": solar.get("assumptions", [])}


def retrieve_plans(state: GraphState) -> dict:
    """Candidate Oncor plans. In MVP read from the seeded electricity_plans table."""
    from app.database import SessionLocal
    from app.models import ElectricityPlan
    db = SessionLocal()
    try:
        rows = db.query(ElectricityPlan).all()
        plans = [{
            "provider": r.provider, "plan_name": r.plan_name, "plan_type": r.plan_type,
            "energy_rate_cents": r.energy_rate_cents,
            "base_charge_monthly": r.base_charge_monthly,
            "buyback_rate_cents": r.buyback_rate_cents or 0.0,
            "buyback_applies_to_tdu": bool(r.buyback_applies_to_tdu),
            "free_nights_start": r.free_nights_start, "free_nights_end": r.free_nights_end,
            "min_usage_fee": r.min_usage_fee or 0.0,
        } for r in rows]
    finally:
        db.close()
    return {"candidate_plans": plans}


def efl_rag_extract(state: GraphState) -> dict:
    """For each candidate plan, confirm/adjust params from its EFL with citations.

    The default already encodes the conservative rule (buyback_applies_to_tdu=False).
    Here we only *upgrade* that flag if the EFL explicitly proves TDU offset.

    Skips RAG entirely when no documents have been ingested — otherwise every run
    fires N pointless embed+Pinecone round trips with nothing to retrieve, which
    makes the inline `/agent/route` energy call slow even with valid keys.
    """
    from app.database import SessionLocal
    from app.models import Document
    db = SessionLocal()
    try:
        has_docs = db.query(Document).count() > 0
    finally:
        db.close()
    if not has_docs:
        return {"plan_params": state.get("candidate_plans", []), "citations": []}

    citations = []
    plan_params = []
    for plan in state.get("candidate_plans", []):
        try:
            chunks = json.loads(_efl_lookup(
                plan_name=plan["plan_name"], provider_name=plan.get("provider"),
                question="Does the solar export credit offset TDU/delivery charges or "
                         "only the energy charge? What is the buyback rate?"))
            proves_tdu = any(
                m.get("text", "").lower().find("offset") >= 0 and
                "deliver" in m.get("text", "").lower()
                for m in chunks.get("matches", []))
            plan["buyback_applies_to_tdu"] = plan.get("buyback_applies_to_tdu") or proves_tdu
            for m in chunks.get("matches", [])[:1]:
                citations.append({"plan": plan["plan_name"], **m.get("citation", {})})
        except Exception:
            # No EFL indexed -> keep conservative defaults.
            pass
        plan_params.append(plan)
    return {"plan_params": plan_params, "citations": citations}


def extract_tdu(state: GraphState) -> dict:
    return {"tdu": json.loads(_tdu_lookup("Oncor"))}


def _build_usage(state: GraphState) -> UsageProfile:
    intake = state.get("intake", {})
    tdu = state.get("tdu", {})
    usage_total = float(intake.get("avg_monthly_usage_kwh") or 1000)
    self_consume = float(intake.get("monthly_self_consume_kwh") or 0)
    export = float(intake.get("monthly_export_kwh") or 0)
    return UsageProfile(
        monthly_usage_kwh=usage_total,
        monthly_import_kwh=max(0.0, usage_total - self_consume),
        monthly_export_kwh=export,
        monthly_self_consume_kwh=self_consume,
        night_share=float(intake.get("night_share") or 0),
        tdu_fixed_monthly=tdu.get("fixed_monthly", 4.23),
        tdu_volumetric_cents=tdu.get("volumetric_cents_per_kwh", 3.60),
    )


def monthly_calc(state: GraphState) -> dict:
    usage = _build_usage(state)
    out = [calc_monthly_bill(PlanParams(**p), usage).to_dict()
           for p in state.get("plan_params", [])]
    return {"monthly_calcs": out}


def annual_calc(state: GraphState) -> dict:
    usage = _build_usage(state)
    out = [calc_annual_bill(PlanParams(**p), usage)
           for p in state.get("plan_params", [])]
    return {"annual_calcs": out}


def rank_plans_node(state: GraphState) -> dict:
    intake = state.get("intake", {})
    current_annual = intake.get("current_annual_bill")
    ranking = rank_plans(
        state.get("annual_calcs", []),
        current_annual=current_annual,
        has_battery=bool(intake.get("battery_installed")),
        has_ev=bool(intake.get("ev_owned")),
    )
    return {"ranking": ranking}


def explain(state: GraphState) -> dict:
    """LLM narrative grounded ONLY in ranking + calc outputs + citations.

    Claude Opus 4.8 (no tools) narrates the engine's numbers; it cannot compute
    or invent figures. See app/agent/explainer.py.
    """
    from app.agent.explainer import generate_explanation
    text = generate_explanation(
        ranking=state.get("ranking", {}),
        assumptions=state.get("assumptions", []),
        citations=state.get("citations", []),
    )
    return {"explanation": text}


def recommend(state: GraphState) -> dict:
    r = state.get("ranking", {})
    rec = {
        "ranked": r.get("ranked", []),
        "best_overall": r.get("best_overall"),
        "best_with_battery": r.get("best_with_battery"),
        "best_without_battery": r.get("best_without_battery"),
        "best_for_ev": r.get("best_for_ev"),
        "explanation": state.get("explanation"),
        "assumptions": state.get("assumptions", []),
        "citations": state.get("citations", []),
    }
    return {"recommendation": rec}


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #
def build_graph():
    g = StateGraph(GraphState)
    g.add_node("collect_user_data", collect_user_data)
    g.add_node("parse_bills", parse_bills)
    g.add_node("ingest_smt", ingest_smt)
    g.add_node("ingest_solar", ingest_solar)
    g.add_node("retrieve_plans", retrieve_plans)
    g.add_node("efl_rag_extract", efl_rag_extract)
    g.add_node("extract_tdu", extract_tdu)
    g.add_node("monthly_calc", monthly_calc)
    g.add_node("annual_calc", annual_calc)
    g.add_node("rank_plans", rank_plans_node)
    g.add_node("explain", explain)
    g.add_node("recommend", recommend)

    g.add_edge(START, "collect_user_data")
    g.add_edge("collect_user_data", "parse_bills")
    g.add_edge("parse_bills", "ingest_smt")
    g.add_edge("ingest_smt", "ingest_solar")
    g.add_edge("ingest_solar", "retrieve_plans")
    g.add_edge("retrieve_plans", "efl_rag_extract")
    g.add_edge("efl_rag_extract", "extract_tdu")
    g.add_edge("extract_tdu", "monthly_calc")
    g.add_edge("monthly_calc", "annual_calc")
    g.add_edge("annual_calc", "rank_plans")
    g.add_edge("rank_plans", "explain")
    g.add_edge("explain", "recommend")
    g.add_edge("recommend", END)
    return g.compile()


GRAPH = build_graph()


def run_comparison(job_id: str, user_id: int, intake: dict) -> dict:
    final = GRAPH.invoke({"job_id": job_id, "user_id": user_id, "intake": intake,
                          "assumptions": [], "citations": [], "errors": []})
    return final.get("recommendation", {})
