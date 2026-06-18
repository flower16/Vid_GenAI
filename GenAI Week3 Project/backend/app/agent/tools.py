"""LangChain StructuredTools.

Tools orchestrate + extract parameters. They NEVER do bill arithmetic themselves —
they delegate to the deterministic calc engine. Each EFL/TDU answer carries a citation.
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from app.calc.engine import (
    PlanParams, UsageProfile, calc_monthly_bill, calc_annual_bill, rank_plans,
)


# --------------------------------------------------------------------------- #
# efl_lookup — grounded RAG answer about ONE plan's terms
# --------------------------------------------------------------------------- #
class EflLookupInput(BaseModel):
    plan_name: str = Field(..., description="Plan to scope the EFL question to")
    provider_name: Optional[str] = None
    question: str = Field(..., description="e.g. 'Does the export credit offset TDU charges?'")


def _efl_lookup(plan_name: str, question: str, provider_name: str | None = None) -> str:
    # Late import to avoid a hard DB dependency when used standalone.
    from app.database import SessionLocal
    from app.rag.retriever import retrieve
    db = SessionLocal()
    try:
        res = retrieve(db, question=question, top_k=4,
                       provider_name=provider_name, plan_name=plan_name)
    finally:
        db.close()
    # The caller (LLM extractor) decides the answer FROM these grounded chunks.
    return json.dumps(res)


efl_lookup = StructuredTool.from_function(
    func=_efl_lookup, name="efl_lookup", args_schema=EflLookupInput,
    description="Retrieve grounded EFL chunks (with citations) to answer a question "
                "about a specific plan's buyback rate, TDU-offset, free-night hours, "
                "or fees. Returns source chunks — do not invent values beyond them.",
)


# --------------------------------------------------------------------------- #
# tdu_charge_lookup — Oncor delivery charges
# --------------------------------------------------------------------------- #
class TduInput(BaseModel):
    tdu_name: str = Field("Oncor")
    as_of_date: Optional[str] = None


def _tdu_lookup(tdu_name: str = "Oncor", as_of_date: str | None = None) -> str:
    from app.database import SessionLocal
    from app.models import TduCharge  # may not exist yet in MVP; fall back to defaults
    try:
        db = SessionLocal()
        row = (db.query(TduCharge)
               .filter(TduCharge.tdu_name == tdu_name)
               .order_by(TduCharge.effective_date.desc()).first())
        db.close()
        if row:
            return json.dumps({"fixed_monthly": row.fixed_monthly,
                               "volumetric_cents_per_kwh": row.volumetric_cents_per_kwh,
                               "source": "sqlite"})
    except Exception:
        pass
    # Conservative published Oncor residential defaults (verify against current tariff).
    return json.dumps({"fixed_monthly": 4.23, "volumetric_cents_per_kwh": 3.60,
                       "source": "default_oncor", "note": "verify against current tariff"})


tdu_charge_lookup = StructuredTool.from_function(
    func=_tdu_lookup, name="tdu_charge_lookup", args_schema=TduInput,
    description="Return Oncor TDU fixed monthly + volumetric delivery charge. "
                "These are NEVER offset by buyback unless an EFL explicitly says so.",
)


# --------------------------------------------------------------------------- #
# calc_monthly / calc_annual / rank — pure delegation to the engine
# --------------------------------------------------------------------------- #
class CalcInput(BaseModel):
    plan: dict = Field(..., description="PlanParams fields")
    usage: dict = Field(..., description="UsageProfile fields")


def _calc_monthly(plan: dict, usage: dict) -> str:
    b = calc_monthly_bill(PlanParams(**plan), UsageProfile(**usage))
    return json.dumps(b.to_dict())


def _calc_annual(plan: dict, usage: dict) -> str:
    return json.dumps(calc_annual_bill(PlanParams(**plan), UsageProfile(**usage)))


calc_monthly_tool = StructuredTool.from_function(
    func=_calc_monthly, name="calc_monthly_bill", args_schema=CalcInput,
    description="Deterministically compute one plan's monthly bill breakdown.")

calc_annual_tool = StructuredTool.from_function(
    func=_calc_annual, name="calc_annual_bill", args_schema=CalcInput,
    description="Deterministically compute one plan's annual bill.")


class RankInput(BaseModel):
    annual_results: list[dict]
    current_annual: Optional[float] = None
    has_battery: bool = False
    has_ev: bool = False


def _rank(annual_results: list[dict], current_annual: float | None = None,
          has_battery: bool = False, has_ev: bool = False) -> str:
    return json.dumps(rank_plans(annual_results, current_annual, has_battery, has_ev))


rank_tool = StructuredTool.from_function(
    func=_rank, name="rank_plans", args_schema=RankInput,
    description="Rank plans by lowest annual cost and tag best-for strategies.")


ALL_TOOLS = [efl_lookup, tdu_charge_lookup, calc_monthly_tool, calc_annual_tool, rank_tool]
