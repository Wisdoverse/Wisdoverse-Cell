"""User-interaction gateway runtime shell."""

from __future__ import annotations

from shared.core import unknown_action_error
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class UserInteractionGatewayAgent(BaseAgent):
    """Thin transport gateway runtime.

    Product conversation, daily-progress, card-operation, and outbox work is
    owned by the chat-agent runtime. This gateway exists to host webhook and
    compatibility HTTP routes without importing chat-agent service internals.
    """

    def __init__(self) -> None:
        super().__init__(
            agent_id="user-interaction-gateway",
            agent_name="User Interaction Gateway",
            subscribed_events=[],
            published_events=[],
        )

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return unknown_action_error()

    async def health_check(self) -> dict[str, bool]:
        return {"gateway": True}


agent = UserInteractionGatewayAgent()


def get_agent() -> UserInteractionGatewayAgent:
    return agent
