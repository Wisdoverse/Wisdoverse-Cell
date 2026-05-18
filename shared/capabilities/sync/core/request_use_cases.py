"""Application use cases for Sync agent requests."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import unknown_action_error


class SyncRequestAgentPort(Protocol):
    """Sync operations required by agent request handling."""

    async def trigger_sync(self, *, triggered_by: str) -> dict[str, Any]:
        """Trigger the compatibility full sync."""

    async def trigger_openproject_sync(self, *, triggered_by: str) -> dict[str, Any]:
        """Trigger OpenProject-to-Bitable sync."""

    async def trigger_feishu_bitable_sync(
        self,
        *,
        triggered_by: str,
    ) -> dict[str, Any]:
        """Trigger Feishu Bitable-to-OpenProject sync."""


class SyncRequestUseCase:
    """Dispatch and execute Sync agent request actions."""

    def __init__(
        self,
        *,
        sync_runner: SyncRequestAgentPort,
        agent_id: str,
    ):
        self._sync_runner = sync_runner
        self._agent_id = agent_id

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "sync_now":
            return await self._sync_runner.trigger_sync(triggered_by="manual")
        if action == "sync_openproject":
            return await self._sync_runner.trigger_openproject_sync(triggered_by="manual")
        if action == "sync_feishu_bitable":
            return await self._sync_runner.trigger_feishu_bitable_sync(
                triggered_by="manual"
            )
        if action == "status":
            return {
                "status": "running",
                "agent_id": self._agent_id,
                "capabilities": ["openproject_sync", "feishu_bitable_sync"],
            }
        return unknown_action_error()
