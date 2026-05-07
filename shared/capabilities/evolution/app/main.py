"""EvolutionModule FastAPI entry point.

CRITICAL: This module must NOT be wrapped with EvolvedAgent (no self-evolution).
Uses create_agent_app with evolution_excluded=True.
"""

from fastapi import APIRouter, Depends

from shared.app import create_agent_app
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key

from ..service.agent import agent

# ── Custom routes ────────────────────────────────────────────────────────────

router = APIRouter()


@router.post("/analyze")
async def trigger_analysis(days: int = 7):
    result = await agent.handle_request({"action": "trigger_analysis", "days": days})
    return result


# ── App ──────────────────────────────────────────────────────────────────────

app = create_agent_app(
    agent,
    title="Evolution Module",
    description="Evolution capability for global trace analysis and architecture recommendations.",
    routers=[(router, [Depends(verify_internal_key)])],
    evolution_excluded=True,  # No self-evolution
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
