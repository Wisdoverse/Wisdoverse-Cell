"""Chat Agent FastAPI entry point (DDD-016 Stage 3 Step 1 skeleton)."""

from shared.app import create_agent_app

from ..service.agent import agent as _raw_agent

agent = _raw_agent
app = create_agent_app(
    agent,
    title="Chat Agent",
)
