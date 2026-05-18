from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.sync.core.event_use_cases import SyncEventUseCase
from shared.schemas.event import Event, EventTypes


def _sync_trigger_event(payload: dict, trace_id: str = "trace_sync") -> Event:
    return Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload=payload,
        trace_id=trace_id,
    )


@pytest.mark.asyncio
async def test_sync_trigger_defaults_to_full_sync() -> None:
    runner = AsyncMock()
    runner.trigger_sync = AsyncMock(return_value={"status": "success"})

    result = await SyncEventUseCase(sync_runner=runner).handle(
        _sync_trigger_event({"triggered_by": "chat_tool"})
    )

    assert result == []
    runner.trigger_sync.assert_awaited_once_with(
        triggered_by="chat_tool",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_sync_trigger_can_run_openproject_boundary() -> None:
    runner = AsyncMock()
    runner.trigger_openproject_sync = AsyncMock(return_value={"status": "success"})

    result = await SyncEventUseCase(sync_runner=runner).handle(
        _sync_trigger_event({"triggered_by": "operator", "scope": "openproject"})
    )

    assert result == []
    runner.trigger_openproject_sync.assert_awaited_once_with(
        triggered_by="operator",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_sync_trigger_can_run_feishu_bitable_boundary() -> None:
    runner = AsyncMock()
    runner.trigger_feishu_bitable_sync = AsyncMock(return_value={"status": "success"})

    result = await SyncEventUseCase(sync_runner=runner).handle(
        _sync_trigger_event({"triggered_by": "operator", "scope": "feishu-bitable"})
    )

    assert result == []
    runner.trigger_feishu_bitable_sync.assert_awaited_once_with(
        triggered_by="operator",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_sync_trigger_uses_payload_default_when_triggered_by_missing() -> None:
    runner = AsyncMock()
    runner.trigger_sync = AsyncMock(return_value={"status": "success"})

    result = await SyncEventUseCase(sync_runner=runner).handle(
        _sync_trigger_event({})
    )

    assert result == []
    runner.trigger_sync.assert_awaited_once_with(
        triggered_by="event",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_sync_trigger_invalid_payload_returns_failed_event() -> None:
    runner = MagicMock()
    runner.trigger_sync = AsyncMock()
    runner.trigger_openproject_sync = AsyncMock()
    runner.trigger_feishu_bitable_sync = AsyncMock()
    runner.create_event.side_effect = lambda event_type, payload, trace_id=None: (
        Event.create(
            event_type=event_type,
            source_agent="sync-module",
            payload=payload,
            trace_id=trace_id,
        )
    )

    result = await SyncEventUseCase(sync_runner=runner).handle(
        _sync_trigger_event({"triggered_by": "operator", "scope": "unknown"})
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.SYNC_FAILED
    assert result[0].metadata.trace_id == "trace_sync"
    assert result[0].payload["scope"] == "invalid"
    assert result[0].payload["error_code"] == "sync_invalid_trigger_payload"


@pytest.mark.asyncio
async def test_non_sync_trigger_event_is_ignored() -> None:
    runner = AsyncMock()
    event = Event.create(
        event_type="unknown.event",
        source_agent="test",
        payload={},
    )

    result = await SyncEventUseCase(sync_runner=runner).handle(event)

    assert result == []
    runner.trigger_sync.assert_not_called()
