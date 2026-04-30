"""EvolutionAgent FastAPI entry point.

CRITICAL: This agent must NOT be wrapped with EvolvedAgent (no self-evolution).
Uses create_agent_app with evolution_excluded=True.
"""

from fastapi import APIRouter, Depends

from shared.app import create_agent_app
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
    title="Evolution Agent",
    description="进化引擎 — 全局追踪分析与架构优化建议",
    routers=[(router, [Depends(verify_internal_key)])],
    evolution_excluded=True,  # No self-evolution
)
