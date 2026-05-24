"""Application use cases for chat-agent scheduled actions."""
from __future__ import annotations

from typing import Any, Protocol


class ChatAgentSchedulerAgentPort(Protocol):
    """Agent operations required by scheduled action use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class ChatAgentSchedulerUseCase:
    """Application boundary for scheduled chat-agent actions."""

    def __init__(self, agent: ChatAgentSchedulerAgentPort):
        self._agent = agent

    async def run_scheduled_action(self, action: str) -> dict[str, Any]:
        return await self._agent.handle_request({"action": action})
