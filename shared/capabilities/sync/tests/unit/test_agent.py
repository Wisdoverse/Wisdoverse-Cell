"""Unit tests for SyncModule lifecycle wiring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.app import UNKNOWN_ACTION_ERROR_CODE
from shared.capabilities.sync.core.sync_ports import SyncEventOutboxStore
from shared.capabilities.sync.service.agent import SyncModule
from shared.schemas.event import Event, EventTypes


class _NoopSyncEventOutboxStore(SyncEventOutboxStore):
    async def add(self, event: Event) -> None:
        pass

    async def list_pending(self, limit: int = 100) -> list[object]:
        return []

    async def mark_published(self, event_id: str) -> None:
        pass

    async def mark_failed(self, event_id: str, error: str) -> None:
        pass


def _sync_module(sync_engine=None) -> SyncModule:
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    agent = SyncModule(
        db=AsyncMock(),
        bus=AsyncMock(),
        event_publisher=publisher,
        outbox_store=_NoopSyncEventOutboxStore(),
    )
    agent._sync_engine = sync_engine
    return agent


def _sync_trigger_event(payload: dict, trace_id: str = "trace_sync") -> Event:
    return Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload=payload,
        trace_id=trace_id,
    )


def test_sync_module_subscribes_to_sync_trigger() -> None:
    agent = SyncModule(db=AsyncMock(), bus=AsyncMock())

    assert EventTypes.SYNC_TRIGGER in agent.subscribed_events


@pytest.mark.asyncio
async def test_shutdown_closes_injected_openproject_port() -> None:
    db = AsyncMock()
    db.close = AsyncMock()
    bus = AsyncMock()
    bus.disconnect = AsyncMock()
    op_client = AsyncMock()
    op_client.close = AsyncMock()

    agent = SyncModule(db=db, bus=bus)
    agent._sync_engine = SimpleNamespace(_op=op_client)

    await agent.shutdown()

    bus.disconnect.assert_awaited_once()
    op_client.close.assert_awaited_once()
    db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_request_can_trigger_openproject_boundary() -> None:
    sync_engine = SimpleNamespace(
        sync_op_to_feishu=AsyncMock(return_value={"status": "success"})
    )
    agent = _sync_module(sync_engine)

    result = await agent.handle_request({"action": "sync_openproject"})

    assert result == {"status": "success"}
    sync_engine.sync_op_to_feishu.assert_awaited_once_with(trace_id=None)


@pytest.mark.asyncio
async def test_handle_request_can_trigger_feishu_bitable_boundary() -> None:
    sync_engine = SimpleNamespace(
        sync_feishu_to_op=AsyncMock(return_value={"status": "success"})
    )
    agent = _sync_module(sync_engine)

    result = await agent.handle_request({"action": "sync_feishu_bitable"})

    assert result == {"status": "success"}
    sync_engine.sync_feishu_to_op.assert_awaited_once_with(trace_id=None)


@pytest.mark.asyncio
async def test_handle_request_unknown_action_uses_shared_error_contract() -> None:
    agent = SyncModule(db=AsyncMock(), bus=AsyncMock())

    result = await agent.handle_request({"action": "invalid"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_defaults_to_full_sync() -> None:
    sync_engine = SimpleNamespace(
        full_sync=AsyncMock(return_value={"status": "success"})
    )
    agent = _sync_module(sync_engine)

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "chat_tool"})
    )

    assert result == []
    sync_engine.full_sync.assert_awaited_once_with(trace_id="trace_sync")


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_can_run_openproject_boundary() -> None:
    sync_engine = SimpleNamespace(
        sync_op_to_feishu=AsyncMock(return_value={"status": "success"})
    )
    agent = _sync_module(sync_engine)

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "openproject"})
    )

    assert result == []
    sync_engine.sync_op_to_feishu.assert_awaited_once_with(trace_id="trace_sync")


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_can_run_feishu_bitable_boundary() -> None:
    sync_engine = SimpleNamespace(
        sync_feishu_to_op=AsyncMock(return_value={"status": "success"})
    )
    agent = _sync_module(sync_engine)

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "feishu-bitable"})
    )

    assert result == []
    sync_engine.sync_feishu_to_op.assert_awaited_once_with(trace_id="trace_sync")


@pytest.mark.asyncio
async def test_trigger_openproject_sync_passes_trace_id_to_split_engine() -> None:
    bus = AsyncMock()
    bus.publish = AsyncMock()
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    agent = SyncModule(
        db=AsyncMock(),
        bus=bus,
        event_publisher=publisher,
        outbox_store=_NoopSyncEventOutboxStore(),
    )
    agent._sync_engine = SimpleNamespace(
        sync_op_to_feishu=AsyncMock(return_value={"status": "success", "processed": 0})
    )

    result = await agent.trigger_openproject_sync(
        triggered_by="operator",
        trace_id="trace_openproject",
    )

    assert result["status"] == "success"
    agent._sync_engine.sync_op_to_feishu.assert_awaited_once_with(
        trace_id="trace_openproject",
    )


@pytest.mark.asyncio
async def test_handle_event_sync_trigger_invalid_payload_returns_failed_event() -> None:
    agent = SyncModule(db=AsyncMock(), bus=AsyncMock())

    result = await agent.handle_event(
        _sync_trigger_event({"triggered_by": "operator", "scope": "unknown"})
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.SYNC_FAILED
    assert result[0].metadata.trace_id == "trace_sync"
    assert result[0].payload["scope"] == "invalid"
    assert result[0].payload["error_code"] == "sync_invalid_trigger_payload"


@pytest.mark.asyncio
async def test_health_check_uses_injected_health_store() -> None:
    health_store = AsyncMock()
    health_store.is_database_ready = AsyncMock(return_value=True)
    agent = SyncModule(
        db=AsyncMock(),
        bus=AsyncMock(),
        health_store=health_store,
    )

    result = await agent.health_check()

    assert result == {"database": True}
    health_store.is_database_ready.assert_awaited_once()
