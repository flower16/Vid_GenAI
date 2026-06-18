"""Deterministic electricity-bill calculation engine.

This module performs ALL bill arithmetic. LLMs/agents never compute money here;
they only supply parameters (extracted + cited from EFLs) and explain results.

Core Texas rule encoded below:
  * Energy charge and TDU delivery charge are SEPARATE.
  * A buyback/export credit reduces the ENERGY charge only, unless the plan's
    EFL explicitly says it offsets delivery (plan.buyback_applies_to_tdu=True).
  * TDU fixed + volumetric charges are paid on every imported kWh regardless.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass
class PlanParams:
    provider: str
    plan_name: str
    plan_type: str                      # 'solar_buyback' | 'free_nights' | 'vpp' | ...
    energy_rate_cents: float            # ¢/kWh on imported energy
    base_charge_monthly: float          # $/mo REP fee
    buyback_rate_cents: float = 0.0     # ¢/kWh credited for exported energy
    buyback_applies_to_tdu: bool = False  # ONLY True if EFL proves it
    free_nights_start: Optional[int] = None  # hour 0-23, inclusive
    free_nights_end: Optional[int] = None    # hour 0-23, exclusive
    min_usage_fee: float = 0.0          # $/mo if below threshold
    min_usage_threshold_kwh: float = 0.0


@dataclass
class UsageProfile:
    monthly_usage_kwh: float            # total consumption
    monthly_import_kwh: float           # grid import (usage - self_consume)
    monthly_export_kwh: float           # solar sent to grid
    monthly_self_consume_kwh: float = 0.0
    night_share: float = 0.0            # fraction of import during free-night window
    tdu_fixed_monthly: float = 4.23     # Oncor default
    tdu_volumetric_cents: float = 3.60  # Oncor default ¢/kWh delivered
    tax_rate: float = 0.0825            # state+local sales tax on the energy bill
    puc_misc_monthly: float = 0.0       # gross receipts / PUC assessment, optional


@dataclass
class BillBreakdown:
    provider: str
    plan_name: str
    plan_type: str
    imported_energy_cost: float
    self_consumption_value: float       # avoided-cost value of solar used on-site
    export_credit: float                # negative reduces bill
    tdu_delivery_cost: float            # fixed + volumetric (NOT offset by export)
    base_fee: float
    taxes_misc: float
    est_monthly_bill: float
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Core calculation
# --------------------------------------------------------------------------- #
def calc_monthly_bill(plan: PlanParams, usage: UsageProfile) -> BillBreakdown:
    assumptions: list[str] = []
    c = 0.01  # cents -> dollars

    billable_import = usage.monthly_import_kwh

    # --- Energy charge (with free-nights handling) ---
    if plan.plan_type == "free_nights" and plan.free_nights_start is not None:
        if usage.night_share <= 0:
            assumptions.append(
                "Free-night usage share not provided; assumed 0% of import is "
                "free — energy cost is conservative (likely overstated)."
            )
        free_kwh = billable_import * max(0.0, min(1.0, usage.night_share))
        paid_kwh = billable_import - free_kwh
        imported_energy_cost = paid_kwh * plan.energy_rate_cents * c
    else:
        imported_energy_cost = billable_import * plan.energy_rate_cents * c

    # --- Export buyback credit (energy-charge offset only, by default) ---
    export_credit = usage.monthly_export_kwh * plan.buyback_rate_cents * c

    # --- TDU delivery (fixed + volumetric on DELIVERED/imported kWh) ---
    tdu_volumetric = billable_import * usage.tdu_volumetric_cents * c
    tdu_delivery_cost = usage.tdu_fixed_monthly + tdu_volumetric

    if plan.buyback_applies_to_tdu:
        # Rare: EFL explicitly offsets delivery too. Cap credit at delivery cost.
        tdu_offset = min(export_credit, tdu_delivery_cost)
        tdu_delivery_cost -= tdu_offset
        assumptions.append(
            "Plan EFL explicitly offsets TDU delivery with export credit "
            "(verified) — delivery reduced accordingly."
        )
    # else: credit applies to energy charge only (default Texas behavior)

    # --- Self-consumption value (informational: avoided import at energy+TDU rate) ---
    self_consumption_value = usage.monthly_self_consume_kwh * (
        plan.energy_rate_cents + usage.tdu_volumetric_cents
    ) * c

    base_fee = plan.base_charge_monthly

    # --- Min-usage fee ---
    if usage.monthly_usage_kwh < plan.min_usage_threshold_kwh:
        base_fee += plan.min_usage_fee
        assumptions.append(
            f"Usage {usage.monthly_usage_kwh} kWh below {plan.min_usage_threshold_kwh} "
            f"kWh threshold; ${plan.min_usage_fee:.2f} min-usage fee applied."
        )

    # --- Pre-tax energy-side subtotal (TDU + base typically taxed too in TX) ---
    pre_tax = imported_energy_cost - export_credit + tdu_delivery_cost + base_fee
    taxes_misc = max(0.0, pre_tax) * usage.tax_rate + usage.puc_misc_monthly

    est_monthly_bill = round(max(0.0, pre_tax + taxes_misc), 2)

    return BillBreakdown(
        provider=plan.provider,
        plan_name=plan.plan_name,
        plan_type=plan.plan_type,
        imported_energy_cost=round(imported_energy_cost, 2),
        self_consumption_value=round(self_consumption_value, 2),
        export_credit=round(export_credit, 2),
        tdu_delivery_cost=round(tdu_delivery_cost, 2),
        base_fee=round(base_fee, 2),
        taxes_misc=round(taxes_misc, 2),
        est_monthly_bill=est_monthly_bill,
        assumptions=assumptions,
    )


def calc_annual_bill(
    plan: PlanParams,
    usage: UsageProfile,
    seasonal_multipliers: Optional[list[float]] = None,
) -> dict:
    """Annual = sum of 12 monthly bills.

    seasonal_multipliers: optional length-12 list scaling usage/production per
    month (TX summers spike A/C use; winter solar dips). Defaults to flat ×1.
    """
    if seasonal_multipliers is None:
        seasonal_multipliers = [1.0] * 12
    assert len(seasonal_multipliers) == 12

    months = []
    annual_total = 0.0
    for m in seasonal_multipliers:
        scaled = UsageProfile(
            monthly_usage_kwh=usage.monthly_usage_kwh * m,
            monthly_import_kwh=usage.monthly_import_kwh * m,
            monthly_export_kwh=usage.monthly_export_kwh * m,
            monthly_self_consume_kwh=usage.monthly_self_consume_kwh * m,
            night_share=usage.night_share,
            tdu_fixed_monthly=usage.tdu_fixed_monthly,
            tdu_volumetric_cents=usage.tdu_volumetric_cents,
            tax_rate=usage.tax_rate,
            puc_misc_monthly=usage.puc_misc_monthly,
        )
        b = calc_monthly_bill(plan, scaled)
        months.append(b.to_dict())
        annual_total += b.est_monthly_bill

    return {
        "provider": plan.provider,
        "plan_name": plan.plan_name,
        "plan_type": plan.plan_type,
        "est_annual_bill": round(annual_total, 2),
        "monthly": months,
        "assumptions": months[0]["assumptions"],
    }


def rank_plans(annual_results: list[dict], current_annual: Optional[float] = None,
               has_battery: bool = False, has_ev: bool = False) -> dict:
    """Sort by lowest annual cost; tag best-for strategies."""
    ranked = sorted(annual_results, key=lambda r: r["est_annual_bill"])
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
        if current_annual is not None:
            r["annual_savings_vs_current"] = round(current_annual - r["est_annual_bill"], 2)

    def best(pred):
        cands = [r for r in ranked if pred(r)]
        return cands[0] if cands else (ranked[0] if ranked else None)

    return {
        "ranked": ranked,
        "best_overall": ranked[0] if ranked else None,
        "best_without_battery": best(lambda r: r["plan_type"] in
                                     ("solar_buyback", "free_nights")),
        "best_with_battery": best(lambda r: "battery" in r["plan_type"]
                                  or r["plan_type"] == "vpp") if has_battery else None,
        "best_for_ev": best(lambda r: r["plan_type"] in
                            ("free_nights", "vpp")) if has_ev else None,
    }
