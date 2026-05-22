"""Tests for the Sync application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.sync.core.application_facade import SyncApplicationFacade
from shared.capabilities.sync.core.sync_ports import SyncEventOutboxStore
from shared.schemas.event import Event, EventTypes


class _OutboxStore(SyncEventOutboxStore):
    def __init__(self, rows=None) -> None:
        self.rows = rows or []
        self.added: list[Event] = []
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.last_limit: int | None = None

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def list_pending(self, limit: int = 100) -> list[object]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


class _HealthStore:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


class _Metrics:
    def __init__(self) -> None:
        self.successes: list[dict] = []
        self.failures: list[dict] = []

    def record_sync_success(self, **kwargs) -> None:
        self.successes.append(kwargs)

    def record_sync_failure(self, **kwargs) -> None:
        self.failures.append(kwargs)


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_sync_01",
        "event_type": EventTypes.SYNC_COMPLETED,
        "source_agent": "sync-module",
        "payload": {"scope": "openproject", "synced_count": 1, "errors": []},
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _event_factory() -> MagicMock:
    factory = MagicMock()

    def create_event(
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="sync-module",
            payload=payload,
            trace_id=trace_id,
        )

    factory.create_event.side_effect = create_event
    return factory


def _facade(
    *,
    sync_engine: MagicMock | None = None,
    outbox_store: _OutboxStore | None = None,
    event_publisher: MagicMock | None = None,
    health_store: _HealthStore | None = None,
    standard_request_handler: AsyncMock | None = None,
    metrics: _Metrics | None = None,
) -> SyncApplicationFacade:
    event_publisher = event_publisher or MagicMock()
    event_publisher.publish = AsyncMock(return_value=True)
    return SyncApplicationFacade(
        agent_id="sync-module",
        standard_request_handler=standard_request_handler or AsyncMock(return_value=None),
        sync_engine_provider=lambda: sync_engine,
        health_store=health_store or _HealthStore(),
        outbox_store_provider=lambda: outbox_store
        if outbox_store is not None
        else _OutboxStore(),
        event_factory=_event_factory(),
        event_publisher=event_publisher,
        metrics=metrics or _Metrics(),
    )


@pytest.mark.asyncio
async def test_sync_application_facade_preserves_standard_request_boundary() -> None:
    standard = AsyncMock(return_value={"status": "standard"})

    result = await _facade(standard_request_handler=standard).handle_request(
        {"action": "describe"}
    )

    assert result == {"status": "standard"}
    standard.assert_awaited_once_with({"action": "describe"})


@pytest.mark.asyncio
async def test_sync_application_facade_dispatches_request_use_case() -> None:
    sync_engine = MagicMock()
    sync_engine.sync_op_to_feishu = AsyncMock(
        return_value={"status": "success", "processed": 3}
    )
    metrics = _Metrics()

    result = await _facade(sync_engine=sync_engine, metrics=metrics).handle_request(
        {"action": "sync_openproject"}
    )

    assert result == {"status": "success", "processed": 3}
    sync_engine.sync_op_to_feishu.assert_awaited_once_with(trace_id=None)
    assert metrics.successes[0]["scope"] == "openproject"


@pytest.mark.asyncio
async def test_sync_application_facade_dispatches_event_use_case() -> None:
    sync_engine = MagicMock()
    sync_engine.sync_feishu_to_op = AsyncMock(
        return_value={"status": "success", "processed": 1}
    )
    event = Event.create(
        event_type=EventTypes.SYNC_TRIGGER,
        source_agent="chat-agent",
        payload={"triggered_by": "operator", "scope": "feishu-bitable"},
        trace_id="trace-sync",
    )

    result = await _facade(sync_engine=sync_engine).handle_event(event)

    assert result == []
    sync_engine.sync_feishu_to_op.assert_awaited_once_with(trace_id="trace-sync")


@pytest.mark.asyncio
async def test_sync_application_facade_delegates_health_check() -> None:
    result = await _facade(health_store=_HealthStore(True)).health_check()

    assert result == {"database": True}


@pytest.mark.asyncio
async def test_sync_application_facade_delegates_outbox_delivery() -> None:
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = _OutboxStore(rows=[_outbox_row(event_id="evt_pending")])
    facade = _facade(outbox_store=outbox_store, event_publisher=publisher)
    event = Event.create(
        event_type=EventTypes.SYNC_STARTED,
        source_agent="sync-module",
        payload={"scope": "openproject", "triggered_by": "test"},
    )

    await facade.publish_sync_event_via_outbox(event)
    result = await facade.publish_pending_sync_events(limit=1)

    assert outbox_store.added == [event]
    assert outbox_store.last_limit == 1
    assert result == {"total": 1, "published": 1, "failed": 0}
    assert publisher.publish.await_count == 2
