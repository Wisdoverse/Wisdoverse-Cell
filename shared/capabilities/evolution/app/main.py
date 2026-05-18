"""EvolutionModule FastAPI entry point.

CRITICAL: This module must NOT be wrapped with EvolvedAgent (no self-evolution).
Uses create_agent_app with evolution_excluded=True.
"""

from fastapi import APIRouter, Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.evolution.db.database import db_manager
from shared.middleware.internal_auth import verify_internal_key

from ..core.api_use_cases import EvolutionApiUseCase
from ..service.agent import agent
from .plugins import EvolutionOutboxDispatcherPlugin

# ── Custom routes ────────────────────────────────────────────────────────────

router = APIRouter()


def get_evolution_api_use_case() -> EvolutionApiUseCase:
    return EvolutionApiUseCase(agent)


@router.post("/analyze")
async def trigger_analysis(
    days: int = 7,
    evolution_api: EvolutionApiUseCase = Depends(get_evolution_api_use_case),
):
    return await evolution_api.trigger_analysis(days=days)


# ── App ──────────────────────────────────────────────────────────────────────

app = create_agent_app(
    agent,
    title="Evolution Module",
    description="Evolution capability for global trace analysis and architecture recommendations.",
    routers=[(router, [Depends(verify_internal_key)])],
    plugins=[
        InfraHealthPlugin(db_manager=db_manager),
        EvolutionOutboxDispatcherPlugin(),
    ],
    evolution_excluded=True,  # No self-evolution
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
