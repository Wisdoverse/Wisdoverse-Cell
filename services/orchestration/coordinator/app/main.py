"""FastAPI entry point for Coordinator Agent."""
from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings

from ..db.database import db_manager
from ..service.agent import CoordinatorAgent
from .plugins import CoordinatorOutboxDispatcherPlugin

agent = CoordinatorAgent(db=db_manager)
app = create_agent_app(
    agent,
    title="Coordinator Agent",
    plugins=[
        InfraHealthPlugin(db_manager=db_manager),
        CoordinatorOutboxDispatcherPlugin(),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
