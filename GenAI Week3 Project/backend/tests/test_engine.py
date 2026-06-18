"""Tests for the deterministic bill engine — the product's credibility core.

The headline rule under test: a buyback credit reduces the ENERGY charge only;
Oncor TDU delivery is NOT offset unless the plan's EFL proves it.
"""
from app.calc.engine import (
    PlanParams, UsageProfile, calc_monthly_bill, calc_annual_bill, rank_plans,
)


def _usage(**kw):
    base = dict(monthly_usage_kwh=1100, monthly_import_kwh=750,
                monthly_export_kwh=600, monthly_self_consume_kwh=350,
                tdu_fixed_monthly=4.23, tdu_volumetric_cents=3.60, tax_rate=0.0)
    base.update(kw)
    return UsageProfile(**base)


def test_tdu_not_offset_by_buyback():
    """Even with a huge export credit, the TDU delivery line is unchanged."""
    plan = PlanParams("TXU", "Solar Buyback", "solar_buyback",
                      energy_rate_cents=16.5, base_charge_monthly=9.95,
                      buyback_rate_cents=16.5)  # generous retail-match
    b = calc_monthly_bill(plan, _usage())
    expected_tdu = 4.23 + 750 * 0.036          # fixed + volumetric on imported kWh
    assert round(b.tdu_delivery_cost, 2) == round(expected_tdu, 2)
    assert b.export_credit == round(600 * 0.165, 2)   # credit is energy-side only


def test_tdu_offset_only_when_efl_proves_it():
    """buyback_applies_to_tdu=True caps the credit against the delivery cost."""
    plan = PlanParams("X", "True 1:1", "solar_buyback",
                      energy_rate_cents=15.0, base_charge_monthly=0.0,
                      buyback_rate_cents=15.0, buyback_applies_to_tdu=True)
    b = calc_monthly_bill(plan, _usage())
    full_tdu = 4.23 + 750 * 0.036
    assert b.tdu_delivery_cost < full_tdu       # delivery WAS reduced
    assert any("offsets TDU" in a for a in b.assumptions)


def test_free_nights_reduces_energy_cost():
    night = PlanParams("REP", "Free Nights", "free_nights",
                       energy_rate_cents=21.0, base_charge_monthly=9.95,
                       free_nights_start=21, free_nights_end=6)
    day_only = calc_monthly_bill(night, _usage(night_share=0.0))
    half_night = calc_monthly_bill(night, _usage(night_share=0.5))
    assert half_night.imported_energy_cost < day_only.imported_energy_cost
    # exactly half the import is free
    assert round(half_night.imported_energy_cost, 2) == round(
        750 * 0.5 * 0.21, 2)


def test_min_usage_fee_applied_below_threshold():
    plan = PlanParams("REP", "Low Use", "solar_buyback",
                      energy_rate_cents=12.0, base_charge_monthly=0.0,
                      min_usage_fee=9.95, min_usage_threshold_kwh=1000)
    below = calc_monthly_bill(plan, _usage(monthly_usage_kwh=800))
    above = calc_monthly_bill(plan, _usage(monthly_usage_kwh=1200))
    assert below.base_fee == 9.95
    assert above.base_fee == 0.0


def test_self_consumption_value_is_informational():
    plan = PlanParams("REP", "P", "solar_buyback", 15.0, 0.0)
    b = calc_monthly_bill(plan, _usage())
    # 350 kWh avoided at (energy + tdu volumetric) rate
    assert round(b.self_consumption_value, 2) == round(
        350 * (15.0 + 3.60) * 0.01, 2)


def test_bill_never_negative():
    plan = PlanParams("REP", "Huge Buyback", "solar_buyback",
                      energy_rate_cents=10.0, base_charge_monthly=0.0,
                      buyback_rate_cents=99.0)
    b = calc_monthly_bill(plan, _usage(monthly_export_kwh=5000))
    assert b.est_monthly_bill >= 0.0


def test_annual_is_twelve_months_flat():
    plan = PlanParams("REP", "P", "solar_buyback", 15.0, 9.95)
    monthly = calc_monthly_bill(plan, _usage())
    annual = calc_annual_bill(plan, _usage())
    assert round(annual["est_annual_bill"], 2) == round(
        monthly.est_monthly_bill * 12, 2)


def test_rank_orders_by_lowest_annual_and_tags():
    plans = [
        PlanParams("A", "Cheap", "solar_buyback", 12.0, 0.0, buyback_rate_cents=12.0),
        PlanParams("B", "Pricey", "solar_buyback", 20.0, 9.95, buyback_rate_cents=3.0),
    ]
    annual = [calc_annual_bill(p, _usage()) for p in plans]
    r = rank_plans(annual, current_annual=2000, has_battery=False, has_ev=False)
    assert r["ranked"][0]["est_annual_bill"] <= r["ranked"][1]["est_annual_bill"]
    assert r["best_overall"]["provider"] == "A"
    assert r["ranked"][0]["annual_savings_vs_current"] > 0
