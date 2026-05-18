from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.capabilities.evolution.core.outbox_delivery_use_cases import (
    EvolutionOutboxDeliveryUseCase,
)
from shared.schemas.event import Event, EventTypes


def _event() -> Event:
    return Event.create(
        event_type=EventTypes.EVOLUTION_SKILL_PROPOSED,
        source_agent="evolution-module",
        payload={"operation": "add_skill"},
        trace_id="trace-evolution",
    )


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_evolution_01",
        "event_type": EventTypes.EVOLUTION_SKILL_PROPOSED,
        "source_agent": "evolution-module",
        "payload": {"operation": "add_skill"},
        "schema_version": "1.0",
        "trace_id": "trace-evolution",
        "correlation_id": None,
        "retry_count": 1,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _use_case(*, outbox_store=None, bus=None, publisher=None):
    if outbox_store is None:
        outbox_store = AsyncMock()
        outbox_store.add = AsyncMock()
        outbox_store.list_pending = AsyncMock(return_value=[])
        outbox_store.mark_published = AsyncMock()
        outbox_store.mark_failed = AsyncMock()
    if bus is None:
        bus = AsyncMock()
        bus.connect = AsyncMock()
    if publisher is None:
        publisher = AsyncMock()
        publisher.publish = AsyncMock(return_value=True)
    return (
        EvolutionOutboxDeliveryUseCase(
            outbox_store=outbox_store,
            event_bus=bus,
            event_publisher=publisher,
        ),
        outbox_store,
        bus,
        publisher,
    )


@pytest.mark.asyncio
async def test_publish_event_via_outbox_stages_before_publish() -> None:
    use_case, outbox_store, bus, publisher = _use_case()
    event = _event()

    ok = await use_case.publish_event_via_outbox(event)

    assert ok is True
    outbox_store.add.assert_awaited_once_with(event)
    bus.connect.assert_awaited_once()
    publisher.publish.assert_awaited_once_with(event)
    outbox_store.mark_published.assert_awaited_once_with(event.event_id)
    outbox_store.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_pending_events_marks_failure_and_continues() -> None:
    publisher = AsyncMock()
    publisher.publish = AsyncMock(side_effect=[False, True])
    use_case, outbox_store, _, _ = _use_case(publisher=publisher)
    outbox_store.list_pending = AsyncMock(
        return_value=[
            _outbox_row(event_id="evt_failed"),
            _outbox_row(event_id="evt_ok"),
        ]
    )

    result = await use_case.publish_pending_events(limit=2)

    outbox_store.list_pending.assert_awaited_once_with(limit=2)
    assert publisher.publish.await_count == 2
    outbox_store.mark_failed.assert_awaited_once()
    outbox_store.mark_published.assert_awaited_once_with("evt_ok")
    assert result == {"total": 2, "published": 1, "failed": 1}


def test_event_from_outbox_preserves_event_contract() -> None:
    use_case, _, _, _ = _use_case()
    row = _outbox_row()

    event = use_case.event_from_outbox(row)

    assert event.event_id == "evt_evolution_01"
    assert event.event_type == EventTypes.EVOLUTION_SKILL_PROPOSED
    assert event.source_agent == "evolution-module"
    assert event.metadata.trace_id == "trace-evolution"
    assert event.metadata.retry_count == 1
