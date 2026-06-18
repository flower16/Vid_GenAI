"""Structured extraction from uploaded bills + solar/SMT data files.

These are deterministic parsers (regex + CSV math), not LLM calls — the values
they return feed the bill engine and current-plan comparison directly.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Optional

# --------------------------------------------------------------------------- #
# Bill PDF parser
# --------------------------------------------------------------------------- #
_MONEY = r"\$?\s*([0-9]+(?:\.[0-9]+)?)"
_CENTS = r"([0-9]+(?:\.[0-9]+)?)\s*(?:¢|cents?|c)/?\s*kwh"

_PATTERNS = {
    "energy_rate_cents": re.compile(r"energy charge[^0-9]*" + _CENTS, re.I),
    "tdu_volumetric_cents": re.compile(
        r"(?:tdu|tdsp|delivery)[^0-9]*" + _CENTS, re.I),
    "base_charge_monthly": re.compile(r"base charge[^0-9]*" + _MONEY, re.I),
    "buyback_rate_cents": re.compile(
        r"(?:buyback|surplus|export credit)[^0-9]*" + _CENTS, re.I),
    "kwh_used": re.compile(r"([0-9,]+)\s*kwh\s*(?:used|usage|consumed)", re.I),
}


def _extract_text(path: str) -> str:
    """Extract text from a PDF using whichever lib is installed."""
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception:
            return ""


def parse_bill_pdf(path: str) -> dict:
    """Return structured fields parsed from a REP bill PDF, with assumptions noted."""
    text = _extract_text(path)
    out: dict = {"source": "bill_pdf", "assumptions": []}
    if not text:
        out["assumptions"].append("Could not extract text from bill PDF; "
                                  "no values parsed.")
        return out

    provider = re.search(r"(TXU|Gexa|Ambit|Rhythm|Reliant|Green Mountain|"
                         r"Tesla)\b", text, re.I)
    if provider:
        out["provider"] = provider.group(1)

    for field, pat in _PATTERNS.items():
        m = pat.search(text)
        if m:
            val = m.group(1).replace(",", "")
            out[field] = float(val)
        else:
            out["assumptions"].append(f"Bill field '{field}' not found in PDF text.")
    return out


# --------------------------------------------------------------------------- #
# Smart Meter Texas usage CSV
# --------------------------------------------------------------------------- #
def load_smt_csv(path_or_text: str, is_text: bool = False) -> dict:
    """Parse SMT interval/daily export into monthly import + export totals.

    SMT exports vary; we look for consumption (kWh) and surplus/generation columns
    case-insensitively. Returns monthly_import_kwh + monthly_export_kwh estimates.
    """
    raw = path_or_text if is_text else open(path_or_text, encoding="utf-8").read()
    reader = csv.DictReader(io.StringIO(raw))
    cols = {c.lower(): c for c in (reader.fieldnames or [])}

    def find(*keys):
        for k in keys:
            for lc, orig in cols.items():
                if k in lc:
                    return orig
        return None

    consume_col = find("consumption", "usage", "kwh_used", "import")
    export_col = find("surplus", "generation", "received", "export")

    total_import = total_export = 0.0
    rows = 0
    for row in reader:
        rows += 1
        try:
            if consume_col and row.get(consume_col):
                total_import += float(row[consume_col].replace(",", ""))
            if export_col and row.get(export_col):
                total_export += float(row[export_col].replace(",", ""))
        except ValueError:
            continue

    out = {"source": "smt", "rows": rows, "assumptions": []}
    # SMT exports are often a full year of daily/interval data -> approx per month.
    months = max(1, rows / 30 / 12 * 12) if rows > 366 else 1
    out["monthly_import_kwh"] = round(total_import / (rows / 30) if rows > 31
                                      else total_import, 1)
    out["monthly_export_kwh"] = round(total_export / (rows / 30) if rows > 31
                                      else total_export, 1)
    if not consume_col:
        out["assumptions"].append("No consumption column found in SMT export.")
    return out


# --------------------------------------------------------------------------- #
# Solar production CSV (Enphase / SolarEdge / Tesla monitoring exports)
# --------------------------------------------------------------------------- #
def load_solar_csv(path_or_text: str, is_text: bool = False) -> dict:
    """Parse solar production export into monthly production / export / self-consume."""
    raw = path_or_text if is_text else open(path_or_text, encoding="utf-8").read()
    reader = csv.DictReader(io.StringIO(raw))
    cols = {c.lower(): c for c in (reader.fieldnames or [])}

    def find(*keys):
        for k in keys:
            for lc, orig in cols.items():
                if k in lc:
                    return orig
        return None

    prod_col = find("production", "produced", "generation", "energy")
    export_col = find("export", "to grid", "exported")
    self_col = find("self", "consumed", "self-consumption")

    prod = exp = selfc = 0.0
    rows = 0
    for row in reader:
        rows += 1
        for col, acc_name in ((prod_col, "prod"), (export_col, "exp"),
                              (self_col, "selfc")):
            if col and row.get(col):
                try:
                    v = float(row[col].replace(",", ""))
                    if acc_name == "prod":
                        prod += v
                    elif acc_name == "exp":
                        exp += v
                    else:
                        selfc += v
                except ValueError:
                    pass

    span = max(1.0, rows / 30) if rows > 31 else 1.0
    out = {
        "source": "solar", "rows": rows, "assumptions": [],
        "monthly_production_kwh": round(prod / span, 1),
        "monthly_export_kwh": round(exp / span, 1),
        "monthly_self_consume_kwh": round(selfc / span, 1),
    }
    if not prod_col:
        out["assumptions"].append("No production column found in solar export.")
    if not self_col and prod_col and export_col:
        out["monthly_self_consume_kwh"] = round((prod - exp) / span, 1)
        out["assumptions"].append("Self-consumption derived as production minus export.")
    return out
