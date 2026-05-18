"""Application use cases for PJM scheduled actions."""
from __future__ import annotations

from typing import Any, Protocol


class PJMSchedulerAgentPort(Protocol):
    """Agent operations required by PJM scheduler use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class PJMSchedulerUseCase:
    """Application boundary for scheduled PJM agent actions."""

    def __init__(self, agent: PJMSchedulerAgentPort):
        self._agent = agent

    async def run_hourly_alerts(self) -> dict[str, Any]:
        result = await self._agent.handle_request({"action": "alerts"})
        alerts = result.get("alerts", [])
        if alerts:
            await self._agent.handle_request({"action": "push_alerts", "alerts": alerts})
        return {"alerts": alerts}

    async def run_scheduled_action(self, action: str) -> dict[str, Any]:
        return await self._agent.handle_request({"action": action})
