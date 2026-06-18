"""Coordinator / router agent (multi-agent layer).

Routes an incoming request to a *domain agent*:
  - energy     -> THIS project's LangGraph comparison (local, fully working)
  - finance    -> an external Financial-RAG project exposed as an MCP server
  - healthcare -> an external Healthcare-analytics project exposed as an MCP server

The external domains are MCP *clients*: each sibling project runs its own MCP
server (same FastMCP pattern as app/mcp/server.py), and this coordinator connects
to it over stdio. Until a project's launch command is configured (FINANCE_MCP_COMMAND
/ HEALTHCARE_MCP_COMMAND), that domain returns a clear "not connected" result — no
fake integration. This is the honest seam: the energy agent is real; the others
light up the moment their projects expose MCP endpoints.
"""
from __future__ import annotations

import asyncio
import re
import shlex
import sys
import threading

from app.config import get_settings

settings = get_settings()

# --- domain classification (deterministic keyword routing; swap for an LLM later) --
_KEYWORDS = {
    "energy": ("electricity", "solar", "kwh", "buyback", "tdu", "oncor",
               "plan", "bill", "battery", "ev", "free night"),
    "finance": ("portfolio", "stock", "invest", "loan", "credit", "10-k",
                "earnings", "valuation", "financial"),
    "healthcare": ("patient", "diagnosis", "clinical", "medical", "ehr",
                   "claims", "icd", "health", "readmission", "readmit",
                   "discharge", "cohort", "comorbid", "hospital"),
}


def _hits(keyword: str, text: str) -> bool:
    # Whole-word match so "ev" doesn't fire inside "revenue", etc.
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def classify_domain(text: str) -> str:
    t = (text or "").lower()
    scores = {d: sum(_hits(k, t) for k in kws) for d, kws in _KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "energy"   # default to this project


# --- external MCP client (stdio) --------------------------------------------- #
async def _call_mcp(command: str, tool: str, arguments: dict) -> dict:
    """Connect to an external project's MCP server over stdio and call one tool."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    # posix=False keeps Windows backslashes intact (paths here contain no spaces).
    parts = shlex.split(command, posix=False)
    params = StdioServerParameters(command=parts[0], args=parts[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return {"content": [c.text for c in result.content
                                if getattr(c, "type", None) == "text"]}


_MCP_TIMEOUT_S = 90   # cap so a missing/broken sibling never hangs the caller


def _run_mcp_call(command: str, tool: str, arguments: dict):
    """Run the async MCP client in a dedicated thread with a subprocess-capable loop.

    Windows: a worker-thread event loop defaults to SelectorEventLoop, which CANNOT
    spawn subprocesses (it just hangs). We force a ProactorEventLoop here so the
    stdio MCP server can be launched regardless of the caller's thread/loop context.
    """
    box: dict = {}

    def worker():
        loop = (asyncio.ProactorEventLoop() if sys.platform == "win32"
                else asyncio.new_event_loop())
        try:
            asyncio.set_event_loop(loop)
            box["value"] = loop.run_until_complete(
                asyncio.wait_for(_call_mcp(command, tool, arguments),
                                 timeout=_MCP_TIMEOUT_S))
        except Exception as e:  # noqa: BLE001
            box["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(_MCP_TIMEOUT_S + 15)
    if "error" in box:
        raise box["error"]
    if "value" not in box:
        raise TimeoutError("MCP worker thread did not finish")
    return box["value"]


def _external(domain: str, command: str, tool: str, arguments: dict) -> dict:
    if not command.strip():
        return {"domain": domain, "status": "not_connected",
                "how_to_enable": f"Set {domain.upper()}_MCP_COMMAND to the launch "
                                 f"command of the {domain} project's MCP server."}
    try:
        return {"domain": domain, "status": "ok",
                "result": _run_mcp_call(command, tool, arguments)}
    except (asyncio.TimeoutError, TimeoutError):
        return {"domain": domain, "status": "error",
                "detail": f"{domain} MCP server did not respond within "
                          f"{_MCP_TIMEOUT_S}s — check that its launch command works "
                          f"and `mcp` is installed in its environment."}
    except Exception as e:  # noqa: BLE001
        return {"domain": domain, "status": "error", "detail": f"{type(e).__name__}: {e}"}


# --- coordinator entry point -------------------------------------------------- #
# Per-domain default MCP tool + argument builder (override via tool/arguments).
_DEFAULT_TOOL = {
    "finance": ("ask_financial", lambda req: {"question": req}),
    "healthcare": ("cohort_readmission_rates", lambda req: {}),
}


def route(request: str, *, intake: dict | None = None,
          tool: str | None = None, arguments: dict | None = None) -> dict:
    """Classify `request` and dispatch to the right domain agent.

    energy: pass `intake` (the 13 user inputs) to run the local comparison.
    finance/healthcare: calls that project's MCP server. `tool`/`arguments` override
    the per-domain default (finance→ask_financial{question}, healthcare→
    cohort_readmission_rates{}).
    """
    domain = classify_domain(request)
    if domain == "energy":
        from app.agent.workflow import run_comparison
        import uuid
        result = run_comparison(str(uuid.uuid4()), user_id=0, intake=intake or {})
        return {"domain": "energy", "status": "ok", "result": result}

    command = (settings.finance_mcp_command if domain == "finance"
               else settings.healthcare_mcp_command)
    default_tool, arg_builder = _DEFAULT_TOOL[domain]
    return _external(domain, command, tool or default_tool,
                     arguments if arguments is not None else arg_builder(request))
