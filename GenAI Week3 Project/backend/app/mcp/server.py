"""SolarBillIQ MCP server (FastMCP, stdio transport).

Exposes the same deterministic capabilities the LangGraph workflow uses as
Model Context Protocol tools, so any MCP client (Claude Desktop, the coordinator
agent, etc.) can call them directly. No logic is duplicated — each tool is a thin
wrapper over the existing engine / lookups / parsers / RAG.

Run standalone:   python -m app.mcp.server
Register in Claude Desktop: see app/mcp/claude_desktop_config.example.json
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from app.calc.engine import (PlanParams, UsageProfile, calc_monthly_bill,
                             calc_annual_bill, rank_plans)
from app.ingest.files import load_smt_csv, load_solar_csv, parse_bill_pdf

mcp = FastMCP("solarbilliq")


# --------------------------------------------------------------------------- #
# Calculation engine
# --------------------------------------------------------------------------- #
@mcp.tool()
def calc_bill(plan: dict, usage: dict) -> dict:
    """Compute one plan's monthly bill breakdown deterministically.

    `plan` = PlanParams fields (provider, plan_name, plan_type, energy_rate_cents,
    base_charge_monthly, buyback_rate_cents, buyback_applies_to_tdu, ...).
    `usage` = UsageProfile fields (monthly_import_kwh, monthly_export_kwh, ...).
    Buyback offsets the energy charge only unless buyback_applies_to_tdu is true.
    """
    return calc_monthly_bill(PlanParams(**plan), UsageProfile(**usage)).to_dict()


@mcp.tool()
def calc_annual(plan: dict, usage: dict) -> dict:
    """Compute one plan's annual bill (sum of 12 monthly bills)."""
    return calc_annual_bill(PlanParams(**plan), UsageProfile(**usage))


@mcp.tool()
def rank(annual_results: list[dict], current_annual: Optional[float] = None,
         has_battery: bool = False, has_ev: bool = False) -> dict:
    """Rank annual results by lowest total cost and tag best-for strategies."""
    return rank_plans(annual_results, current_annual, has_battery, has_ev)


# --------------------------------------------------------------------------- #
# Lookups (SQLite catalog)
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdu_lookup(tdu_name: str = "Oncor") -> dict:
    """Return the TDU fixed monthly + volumetric delivery charge (default Oncor)."""
    from app.database import SessionLocal
    from app.models import TduCharge
    db = SessionLocal()
    try:
        row = (db.query(TduCharge).filter(TduCharge.tdu_name == tdu_name)
               .order_by(TduCharge.effective_date.desc()).first())
        if row:
            return {"tdu_name": tdu_name, "fixed_monthly": row.fixed_monthly,
                    "volumetric_cents_per_kwh": row.volumetric_cents_per_kwh}
    finally:
        db.close()
    return {"tdu_name": tdu_name, "fixed_monthly": 4.23,
            "volumetric_cents_per_kwh": 3.60, "note": "default — verify against tariff"}


@mcp.tool()
def plan_lookup() -> list[dict]:
    """List the known Oncor-area electricity plans from the catalog."""
    from app.database import SessionLocal
    from app.models import ElectricityPlan
    db = SessionLocal()
    try:
        return [{
            "provider": p.provider, "plan_name": p.plan_name, "plan_type": p.plan_type,
            "energy_rate_cents": p.energy_rate_cents,
            "base_charge_monthly": p.base_charge_monthly,
            "buyback_rate_cents": p.buyback_rate_cents,
            "buyback_applies_to_tdu": bool(p.buyback_applies_to_tdu),
        } for p in db.query(ElectricityPlan).all()]
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# File parsers
# --------------------------------------------------------------------------- #
@mcp.tool()
def parse_solar(path: str) -> dict:
    """Parse a solar production CSV into monthly production/export/self-consume."""
    return load_solar_csv(path)


@mcp.tool()
def parse_smt(path: str) -> dict:
    """Parse a Smart Meter Texas CSV into monthly grid import/export."""
    return load_smt_csv(path)


@mcp.tool()
def parse_bill(path: str) -> dict:
    """Parse a REP electricity-bill PDF into structured rate fields."""
    return parse_bill_pdf(path)


# --------------------------------------------------------------------------- #
# RAG retrieval (graceful if Pinecone/OpenAI keys aren't configured)
# --------------------------------------------------------------------------- #
@mcp.tool()
def efl_search(question: str, plan_name: Optional[str] = None,
               provider_name: Optional[str] = None, top_k: int = 4) -> dict:
    """Retrieve grounded EFL chunks (with citations) for a plan-terms question."""
    try:
        from app.database import SessionLocal
        from app.rag.retriever import retrieve
        db = SessionLocal()
        try:
            return retrieve(db, question=question, top_k=top_k,
                            plan_name=plan_name, provider_name=provider_name)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable",
                "detail": f"RAG not configured ({type(e).__name__}). "
                          "Set PINECONE_API_KEY + OPENAI_API_KEY and ingest EFLs."}


if __name__ == "__main__":
    mcp.run()  # stdio transport
