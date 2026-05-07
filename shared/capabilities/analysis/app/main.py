"""Analysis capability FastAPI entry point."""

from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key

from ..api.analysis import router as analysis_router
from ..service.agent import agent as _raw_agent

app = create_agent_app(
    _raw_agent,
    title="Analysis Module",
    description="Analysis capability for daily reports, weekly reports, milestones, and quality review.",
    routers=[(analysis_router, [Depends(verify_internal_key)])],
    plugins=[InfraHealthPlugin()],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
