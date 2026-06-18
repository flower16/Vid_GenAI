"""TEMPLATE — drop into a sibling project to MCP-enable it.

Copy this to <that project>/mcp/server.py, replace the imports + tool bodies with
that project's real functions, then run:  python -m mcp.server

Register it with the SolarBillIQ coordinator by setting, in this repo's backend/.env:
    FINANCE_MCP_COMMAND=python -m mcp.server          # run from the project's dir
    # or HEALTHCARE_MCP_COMMAND=...

The coordinator (app/agent/router.py) launches this command over stdio and calls
the tools below. Each @mcp.tool() function becomes callable by name.
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

# 1) Import THIS project's real functions, e.g.:
# from finance_rag.pipeline import answer_question, retrieve_docs
# from healthcare.analytics import summarize_claims, compute_metrics

mcp = FastMCP("finance")          # <- name this project's domain ("finance"/"healthcare")


@mcp.tool()
def answer(question: str, top_k: int = 5) -> dict:
    """One-line description of what this project answers.

    The docstring + type hints become the tool's schema the calling model reads,
    so make them precise. Replace the body with a call into the real pipeline.
    """
    # return answer_question(question, top_k=top_k)
    return {"status": "stub", "question": question,
            "detail": "Replace with this project's real entrypoint."}


@mcp.tool()
def analyze(file_path: str, metric: Optional[str] = None) -> dict:
    """Run an analysis over a file this project understands (CSV, PDF, …)."""
    # return compute_metrics(file_path, metric=metric)
    return {"status": "stub", "file_path": file_path, "metric": metric}


if __name__ == "__main__":
    mcp.run()   # stdio transport — what the coordinator connects to
