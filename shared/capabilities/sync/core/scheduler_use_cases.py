"""Application use cases for Sync scheduled operations."""
from __future__ import annotations

from typing import Any, Protocol


class SyncSchedulerAgentPort(Protocol):
    """Agent operations required by Sync scheduler use cases."""

    async def trigger_sync(self, *, triggered_by: str) -> dict[str, Any]:
        """Trigger the compatibility full sync."""


class SyncSchedulerUseCase:
    """Application boundary for scheduled Sync operations."""

    def __init__(self, agent: SyncSchedulerAgentPort):
        self._agent = agent

    async def run_scheduled_sync(self) -> dict[str, Any]:
        return await self._agent.trigger_sync(triggered_by="scheduler")
