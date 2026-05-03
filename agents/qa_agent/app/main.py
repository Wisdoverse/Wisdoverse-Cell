"""QA Agent FastAPI application entry point."""

from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key

from ..api.qa import router as qa_router
from ..service.agent import agent as _raw_agent

app = create_agent_app(
    _raw_agent,
    title="QA Agent",
    description="Automated acceptance verification for AI-generated code",
    routers=[
        (qa_router, [Depends(verify_internal_key)]),
    ],
    plugins=[
        InfraHealthPlugin(
            check_nats=settings.event_bus_backend == "nats",
        ),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
