"""LLM explanation generation via Claude Opus 4.8 (official Anthropic SDK).

CRITICAL: the model only *narrates* numbers the deterministic engine already
computed. It is given the ranking JSON + assumptions + citations and is
forbidden from inventing or recomputing any figure. No tools are bound, so it
cannot perform actions — it returns prose only.
"""
from __future__ import annotations

import json

import anthropic

from app.config import get_settings

settings = get_settings()

_SYSTEM = """You are an energy analyst explaining an electricity-plan comparison \
for a rooftop-solar home in Frisco, TX (Oncor TDU territory).

Hard rules:
- Use ONLY the numbers in the provided JSON. Never invent, round differently, \
or recompute any dollar figure — quote them as given.
- Buyback credits offset the ENERGY charge only. State explicitly that Oncor TDU \
delivery charges are NOT reduced by solar export unless a plan's data says \
buyback_applies_to_tdu is true.
- Clearly separate energy charges from TDU delivery charges.
- Surface every item in `assumptions` so the reader knows what was estimated.
- Be concise: lead with the recommended plan and its annual cost, then why."""


_PLACEHOLDERS = {"", "your-anthropic-key", "your-api-key", "changeme"}


def _fallback(ranking: dict, note: str = "") -> str:
    best = (ranking.get("best_overall") or {})
    prefix = f"[{note}] " if note else ""
    return (f"{prefix}Lowest annual cost: {best.get('provider')} "
            f"{best.get('plan_name')} at ${best.get('est_annual_bill')}/yr. "
            f"Buyback offsets energy charges only; Oncor TDU delivery is not reduced.")


def generate_explanation(ranking: dict, assumptions: list[str],
                         citations: list[dict]) -> str:
    """Return a grounded narrative; degrade to a deterministic string on any failure.

    A missing/placeholder key or an API error must NOT break the comparison — the
    ranking is already computed deterministically; this only narrates it.
    """
    key = (settings.anthropic_api_key or "").strip()
    if key in _PLACEHOLDERS:
        return _fallback(ranking, "LLM disabled — set ANTHROPIC_API_KEY")

    payload = json.dumps({"ranking": ranking, "assumptions": assumptions,
                          "citations": citations}, default=str)
    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1500,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": "Explain and recommend based strictly on this JSON. "
                           "Do not introduce any number not present here.\n\n" + payload,
            }],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:  # noqa: BLE001 — never let narration break the run
        return _fallback(ranking, f"LLM unavailable: {type(e).__name__}")
