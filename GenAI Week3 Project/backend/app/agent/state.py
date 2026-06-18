"""Shared LangGraph state object passed between all 12 nodes."""
from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict
from operator import add


class GraphState(TypedDict, total=False):
    job_id: str
    user_id: int

    # 1) collected user data (the 13 intake inputs)
    intake: dict
    missing_fields: list[str]

    # 2-4) ingested file outputs
    parsed_bill: Optional[dict]
    smt_usage: Optional[dict]
    solar_production: Optional[dict]

    # 5) candidate plans for Oncor
    candidate_plans: list[dict]

    # 6) per-plan EFL-extracted params (each w/ citations)
    plan_params: list[dict]

    # 7) Oncor TDU charges
    tdu: dict

    # 8-9) calculations
    monthly_calcs: list[dict]
    annual_calcs: list[dict]

    # 10) ranking + strategy tags
    ranking: dict

    # 11-12) outputs
    explanation: str
    recommendation: dict

    # cross-cutting: assumptions accumulate across nodes (reducer = list concat)
    assumptions: Annotated[list[str], add]
    citations: Annotated[list[dict], add]
    errors: Annotated[list[str], add]
