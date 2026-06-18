"""Seed the electricity_plans + tdu_charges tables with Oncor-area solar plans.

⚠️  RATES ARE APPROXIMATE (from public 2026 comparison sites, June 2026) and MUST be
    verified against each plan's current EFL before relying on them. The RAG layer
    (efl_rag_extract node) is what should ultimately confirm/override these values.

Sources used to seed (see chat summary):
  - nuwattenergy.com/en/texas/solar-buyback-rates-2026
  - choosetexaspower.org/solar-buyback-plans
  - quickelectricity.com/texas-solar-buyback-net-metering-programs

Key facts encoded:
  - buyback_applies_to_tdu = False for ALL plans (no TX plan offsets Oncor delivery
    unless its EFL explicitly says so — none of these do).
  - "1:1 / retail-match" plans credit exports at ~the energy rate (energy charge only).

    Run:  python seed_plans.py
"""
from app.database import SessionLocal, init_db
from app.models import ElectricityPlan, TduCharge

PLANS = [
    # provider, plan_name, type, energy¢, base$, buyback¢, notes
    dict(provider="TXU Energy", plan_name="TXU Solar Buyback 12", plan_type="solar_buyback",
         energy_rate_cents=16.5, base_charge_monthly=9.95, buyback_rate_cents=16.5,
         buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.txu.com"),  # retail-match ~1:1
    dict(provider="Gexa Energy", plan_name="Gexa Solar Export 12", plan_type="solar_buyback",
         energy_rate_cents=15.9, base_charge_monthly=0.0, buyback_rate_cents=3.0,
         buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.gexaenergy.com"),  # no rollover
    dict(provider="Ambit Energy", plan_name="Ambit Solar Buyback", plan_type="solar_buyback",
         energy_rate_cents=17.0, base_charge_monthly=4.95, buyback_rate_cents=12.5,
         buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.ambitenergy.com"),  # high fixed
    dict(provider="Rhythm", plan_name="Rhythm Solar Buyback (rollover)", plan_type="solar_buyback",
         energy_rate_cents=15.5, base_charge_monthly=0.0, buyback_rate_cents=12.0,
         buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.gotrhythm.com"),  # credits roll over
    dict(provider="TXU Energy", plan_name="TXU Free Nights & Solar", plan_type="free_nights",
         energy_rate_cents=21.0, base_charge_monthly=9.95, buyback_rate_cents=0.0,
         free_nights_start=21, free_nights_end=6, buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.txu.com"),
    dict(provider="Tesla Electric", plan_name="Tesla VPP / Battery", plan_type="vpp",
         energy_rate_cents=14.0, base_charge_monthly=9.95, buyback_rate_cents=10.0,
         buyback_applies_to_tdu=False,
         efl_effective_date="2026", source_url="https://www.tesla.com/support/energy"),
]


def main():
    init_db()
    db = SessionLocal()
    try:
        if not db.query(TduCharge).first():
            db.add(TduCharge(tdu_name="Oncor", fixed_monthly=4.23,
                             volumetric_cents_per_kwh=3.60, effective_date="2026"))
        for p in PLANS:
            exists = db.query(ElectricityPlan).filter_by(plan_name=p["plan_name"]).first()
            if not exists:
                db.add(ElectricityPlan(**p))
        db.commit()
        print(f"Seeded {len(PLANS)} plans + Oncor TDU charges.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
