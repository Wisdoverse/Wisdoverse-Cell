"""Chat Agent runtime (DDD-016 Stage 3 Step 1 skeleton).

Skeleton BaseAgent subclass. Subscribes to no events yet — that
lands in Step 3 when `chat_service.py` migrates from
`services/gateways/user_interaction/`. Per ADR-0010 Step 1 the
skeleton ships first so subsequent table + logic moves have a
landing site without breaking the gateway.
"""

from __future__ import annotations

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("chat_agent.service")


class ChatAgent(BaseAgent):
    """Skeleton chat-agent runtime.

    Owns the `chat-agent` canonical runtime ID (AGENTS.md Part 3
    rule 13). Tables, ports, and use cases migrate in the
    subsequent ADR-0010 steps.
    """

    def __init__(self) -> None:
        super().__init__(
            agent_id="chat-agent",
            agent_name="Chat Agent",
            subscribed_events=(),
            published_events=(),
        )

    async def startup(self) -> None:
        logger.info("chat_agent_skeleton_starting", agent_id=self.agent_id)

    async def shutdown(self) -> None:
        logger.info("chat_agent_skeleton_stopping", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        """No-op until ADR-0010 Step 3 migrates the chat business logic."""
        return []

    async def handle_request(self, request: dict) -> dict:
        """No-op until ADR-0010 Step 3 migrates the chat business logic."""
        return {"status": "skeleton"}


agent = ChatAgent()


def get_agent() -> ChatAgent:
    return agent
