"""FastAPI entry point for Coordinator Agent."""
from shared.app import create_agent_app

from ..service.agent import CoordinatorAgent

agent = CoordinatorAgent()
app = create_agent_app(agent, title="Coordinator Agent")
