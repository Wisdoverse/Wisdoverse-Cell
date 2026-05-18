"""Application use cases for user-interaction scheduled actions."""
from __future__ import annotations

from typing import Any, Protocol


class UserInteractionSchedulerAgentPort(Protocol):
    """Agent operations required by scheduled action use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class UserInteractionSchedulerUseCase:
    """Application boundary for scheduled user-interaction agent actions."""

    def __init__(self, agent: UserInteractionSchedulerAgentPort):
        self._agent = agent

    async def run_scheduled_action(self, action: str) -> dict[str, Any]:
        return await self._agent.handle_request({"action": action})
