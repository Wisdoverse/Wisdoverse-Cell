"""Application use cases for Sync event dispatch."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from shared.schemas.event import Event, EventTypes
from shared.schemas.event_payloads import SyncTriggerPayload


class SyncEventRunnerPort(Protocol):
    async def trigger_sync(
        self,
        *,
        triggered_by: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger the compatibility full sync."""

    async def trigger_openproject_sync(
        self,
        *,
        triggered_by: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger OpenProject-to-Bitable sync."""

    async def trigger_feishu_bitable_sync(
        self,
        *,
        triggered_by: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger Feishu Bitable-to-OpenProject sync."""

    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        """Create an event emitted by the Sync capability."""


class SyncEventUseCase:
    """Handle sync.trigger events outside the service shell."""

    def __init__(self, *, sync_runner: SyncEventRunnerPort):
        self._sync_runner = sync_runner

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type != EventTypes.SYNC_TRIGGER:
            return []

        trace_id = event.metadata.trace_id if event.metadata else None
        try:
            payload = SyncTriggerPayload.model_validate(event.payload)
        except ValidationError as exc:
            return [
                self._sync_runner.create_event(
                    EventTypes.SYNC_FAILED,
                    {
                        "scope": "invalid",
                        "error": f"Invalid sync.trigger payload: {exc.errors()[0]['msg']}",
                        "error_code": "sync_invalid_trigger_payload",
                    },
                    trace_id=trace_id,
                )
            ]

        raw_scope = payload.scope or payload.target or "full"
        scope = self._normalize_sync_scope(raw_scope)
        if scope is None:
            return [
                self._sync_runner.create_event(
                    EventTypes.SYNC_FAILED,
                    {
                        "scope": raw_scope,
                        "error": f"Unsupported sync.trigger scope: {raw_scope}",
                        "error_code": "sync_unsupported_scope",
                    },
                    trace_id=trace_id,
                )
            ]

        triggered_by = payload.triggered_by or event.source_agent or "event"
        if scope == "openproject":
            await self._sync_runner.trigger_openproject_sync(
                triggered_by=triggered_by,
                trace_id=trace_id,
            )
        elif scope == "feishu_bitable":
            await self._sync_runner.trigger_feishu_bitable_sync(
                triggered_by=triggered_by,
                trace_id=trace_id,
            )
        else:
            await self._sync_runner.trigger_sync(
                triggered_by=triggered_by,
                trace_id=trace_id,
            )
        return []

    @staticmethod
    def _normalize_sync_scope(scope: str) -> str | None:
        normalized = scope.replace("-", "_").lower()
        if normalized in {"full", "openproject", "feishu_bitable"}:
            return normalized
        return None
