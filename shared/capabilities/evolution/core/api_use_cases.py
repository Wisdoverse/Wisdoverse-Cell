"""Application use cases for Evolution HTTP operations."""
from __future__ import annotations

from typing import Any, Protocol


class EvolutionApiAgentPort(Protocol):
    """Agent operations required by Evolution HTTP application use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class EvolutionApiUseCase:
    """Application boundary used by Evolution HTTP routes."""

    def __init__(self, agent: EvolutionApiAgentPort):
        self._agent = agent

    async def trigger_analysis(self, *, days: int) -> dict[str, Any]:
        return await self._agent.handle_request(
            {"action": "trigger_analysis", "days": days}
        )
