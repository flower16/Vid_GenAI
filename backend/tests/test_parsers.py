"""Tests for the deterministic file parsers (solar / SMT / bill)."""
import app.ingest.files as files
from app.ingest.files import load_solar_csv, load_smt_csv, parse_bill_pdf

SOLAR = ("Date,Production (kWh),Exported (kWh)\n"
         "2026-05-01,30,20\n2026-05-02,30,18\n")
SOLAR_NO_SELF = SOLAR  # self-consume derived from prod - export

SMT = ("Date,Consumption (kWh),Surplus Generation (kWh)\n"
       "2026-05-01,36,20\n2026-05-02,34,18\n")


def test_solar_sums_one_month_and_derives_self_consumption():
    out = load_solar_csv(SOLAR, is_text=True)
    assert out["monthly_production_kwh"] == 60.0
    assert out["monthly_export_kwh"] == 38.0
    # self-consume derived as production - export
    assert out["monthly_self_consume_kwh"] == 22.0
    assert any("production minus export" in a for a in out["assumptions"])


def test_smt_sums_import_and_export():
    out = load_smt_csv(SMT, is_text=True)
    assert out["monthly_import_kwh"] == 70.0
    assert out["monthly_export_kwh"] == 38.0
    assert out["assumptions"] == []


def test_smt_flags_missing_consumption_column():
    out = load_smt_csv("Date,Foo\n2026-05-01,1\n", is_text=True)
    assert any("No consumption column" in a for a in out["assumptions"])


def test_bill_parser_extracts_fields(monkeypatch):
    """Drive the regex without a real PDF by stubbing text extraction."""
    sample = (
        "TXU Energy   Account Summary\n"
        "Energy Charge: 16.5 cents/kWh\n"
        "TDU Delivery Charge 3.60 c/kWh\n"
        "Base Charge: $9.95\n"
        "Surplus Credit 16.5 cents/kWh\n"
        "1,100 kWh used\n"
    )
    monkeypatch.setattr(files, "_extract_text", lambda p: sample)
    out = parse_bill_pdf("ignored.pdf")
    assert out["provider"].upper() == "TXU"
    assert out["energy_rate_cents"] == 16.5
    assert out["base_charge_monthly"] == 9.95
    assert out["buyback_rate_cents"] == 16.5
    assert out["kwh_used"] == 1100.0


def test_bill_parser_handles_unreadable_pdf(monkeypatch):
    monkeypatch.setattr(files, "_extract_text", lambda p: "")
    out = parse_bill_pdf("ignored.pdf")
    assert any("Could not extract text" in a for a in out["assumptions"])
