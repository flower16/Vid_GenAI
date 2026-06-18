"""Multi-agent coordinator endpoint.

Exposes the domain router over HTTP so the UI / any client can send a natural-
language request and have it dispatched to the right domain agent (energy local,
finance/healthcare via external MCP servers).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.agent.router import classify_domain, route
from app.models import User

router = APIRouter(prefix="/agent", tags=["agent"])


class RoutePayload(BaseModel):
    request: str                       # natural-language request to classify + dispatch
    intake: dict | None = None         # energy domain: the comparison inputs
    tool: str | None = None            # finance/healthcare: override the MCP tool
    arguments: dict | None = None      # finance/healthcare: override the tool args


@router.post("/route")
def route_request(payload: RoutePayload, user: User = Depends(get_current_user)):
    """Classify the request and dispatch to the matching domain agent."""
    return route(payload.request, intake=payload.intake,
                 tool=payload.tool, arguments=payload.arguments)


@router.post("/classify")
def classify(payload: RoutePayload, user: User = Depends(get_current_user)):
    """Return just the routing decision (no dispatch) — useful for previews/UI."""
    return {"request": payload.request, "domain": classify_domain(payload.request)}
