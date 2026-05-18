"""Application use cases for Sync HTTP operations."""
from __future__ import annotations

from typing import Any, Protocol


class SyncApiAgentPort(Protocol):
    """Agent operations required by the Sync HTTP application use cases."""

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

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


class SyncApiUseCase:
    """Application boundary used by Sync HTTP routes."""

    def __init__(self, agent: SyncApiAgentPort):
        self._agent = agent

    async def trigger_sync(self) -> dict[str, Any]:
        result = await self._agent.trigger_sync(triggered_by="api")
        return self._normalize_trigger_result(result)

    async def trigger_openproject_sync(self) -> dict[str, Any]:
        result = await self._agent.trigger_openproject_sync(triggered_by="api")
        return self._normalize_trigger_result(result)

    async def trigger_feishu_bitable_sync(self) -> dict[str, Any]:
        result = await self._agent.trigger_feishu_bitable_sync(triggered_by="api")
        return self._normalize_trigger_result(result)

    async def get_status(self) -> dict[str, Any]:
        return await self._agent.handle_request({"action": "status"})

    def _normalize_trigger_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("status", "completed"),
            "total_processed": result.get(
                "total_processed",
                result.get("processed", 0),
            ),
            "errors": result.get("errors", []),
            "error": result.get("error"),
        }
