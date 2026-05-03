"""Unit tests for SyncAgent lifecycle wiring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.sync.service.agent import SyncAgent
from shared.schemas.event import Event, EventTypes


def _sync_trigger_event(payload: dict, trace_id: str = "trace_sync") -> Event:
    return Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload=payload,
        trace_id=trace_id,
    )


def test_sync_agent_subscribes_to_sync_trigger() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())

    assert EventTypes.SYNC_TRIGGER in agent.subscribed_events


@pytest.mark.asyncio
async def test_shutdown_closes_injected_openproject_port() -> None:
    db = AsyncMock()
    db.close = AsyncMock()
    bus = AsyncMock()
    bus.disconnect = AsyncMock()
    op_client = AsyncMock()
    op_client.close = AsyncMock()

    agent = SyncAgent(db=db, bus=bus)
    agent._sync_engine = SimpleNamespace(_op=op_client)

    await agent.shutdown()

    bus.disconnect.assert_awaited_once()
    op_client.close.assert_awaited_once()
    db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_request_can_trigger_openproject_boundary() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())
    agent.trigger_openproject_sync = AsyncMock(return_value={"status": "success"})

    result = await agent.handle_request({"action": "sync_openproject"})

    assert result == {"status": "success"}
    agent.trigger_openproject_sync.assert_awaited_once_with(triggered_by="manual")


@pytest.mark.asyncio
async def test_handle_request_can_trigger_feishu_bitable_boundary() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())
    agent.trigger_feishu_bitable_sync = AsyncMock(return_value={"status": "success"})

    result = await agent.handle_request({"action": "sync_feishu_bitable"})

    assert result == {"status": "success"}
    agent.trigger_feishu_bitable_sync.assert_awaited_once_with(triggered_by="manual")


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_defaults_to_full_sync() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())
    agent.trigger_sync = AsyncMock(return_value={"status": "success"})

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "chat_tool"})
    )

    assert result == []
    agent.trigger_sync.assert_awaited_once_with(
        triggered_by="chat_tool",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_can_run_openproject_boundary() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())
    agent.trigger_openproject_sync = AsyncMock(return_value={"status": "success"})

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "openproject"})
    )

    assert result == []
    agent.trigger_openproject_sync.assert_awaited_once_with(
        triggered_by="operator",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_can_run_feishu_bitable_boundary() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())
    agent.trigger_feishu_bitable_sync = AsyncMock(return_value={"status": "success"})

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "feishu-bitable"})
    )

    assert result == []
    agent.trigger_feishu_bitable_sync.assert_awaited_once_with(
        triggered_by="operator",
        trace_id="trace_sync",
    )


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_invalid_payload_returns_failed_event() -> None:
    agent = SyncAgent(db=AsyncMock(), bus=AsyncMock())

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "unknown"})
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.SYNC_FAILED
    assert result[0].metadata.trace_id == "trace_sync"
    assert result[0].payload["scope"] == "invalid"
