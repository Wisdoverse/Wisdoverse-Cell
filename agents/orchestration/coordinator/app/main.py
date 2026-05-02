"""FastAPI entry point for Coordinator Agent."""
from shared.app import create_agent_app
from shared.config import settings

from ..service.agent import CoordinatorAgent

agent = CoordinatorAgent()
app = create_agent_app(
    agent,
    title="Coordinator Agent",
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
