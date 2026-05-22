"""Tests for the Coordinator application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.orchestration.coordinator.core.application_facade import (
    CoordinatorApplicationFacade,
)
from services.orchestration.coordinator.core.models import Decision
from services.orchestration.coordinator.core.outbox_ports import (
    CoordinatorEventOutboxStore,
)
from shared.app import UNKNOWN_ACTION_ERROR_CODE
from shared.schemas.event import Event, EventTypes


class _Scratchpad:
    def __init__(self, initialized: bool = True) -> None:
        self._initialized = initialized
        self.updated: list[list[Decision]] = []

    def is_initialized(self) -> bool:
        return self._initialized

    async def read_incremental(self) -> str:
        return ""

    async def update(self, decisions: list[Decision]) -> None:
        self.updated.append(decisions)

    def should_compact(self) -> bool:
        return False

    async def compact(self) -> None:
        pass


class _HealthStore:
    async def is_database_ready(self) -> bool:
        return True


class _OutboxStore(CoordinatorEventOutboxStore):
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


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_coord_01",
        "event_type": EventTypes.COORDINATOR_DISPATCH,
        "source_agent": "coordinator",
        "payload": {
            "target_agent": "requirement-manager",
            "task_id": "task_001",
            "instruction": "Produce PRD",
        },
        "schema_version": "1.0",
        "trace_id": None,
        "correlation_id": None,
        "retry_count": 0,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _facade(
    *,
    scratchpad: _Scratchpad | None = None,
    state_store: MagicMock | None = None,
    thinker: AsyncMock | None = None,
    outbox_store: _OutboxStore | None = None,
    event_bus: MagicMock | None = None,
    event_publisher: MagicMock | None = None,
    standard_request_handler: AsyncMock | None = None,
    database_enabled: bool = True,
) -> CoordinatorApplicationFacade:
    scratchpad = scratchpad or _Scratchpad()
    state_store = state_store or MagicMock()
    state_store.get_agent_states = AsyncMock(return_value={})
    state_store.get_pending_decisions = AsyncMock(return_value=[])
    state_store.persist = AsyncMock()
    thinker = thinker or AsyncMock(return_value=[])
    event_bus = event_bus or MagicMock()
    event_bus.connect = AsyncMock()
    event_publisher = event_publisher or MagicMock()
    event_publisher.publish = AsyncMock(return_value=True)

    return CoordinatorApplicationFacade(
        standard_request_handler=standard_request_handler or AsyncMock(return_value=None),
        scratchpad_provider=lambda: scratchpad,
        state_store_provider=lambda: state_store,
        thinker_provider=lambda: thinker,
        llm_gateway_provider=lambda: object(),
        database_enabled=database_enabled,
        health_store_provider=lambda: _HealthStore(),
        outbox_store_provider=lambda: outbox_store if outbox_store is not None else _OutboxStore(),
        event_bus=event_bus,
        event_publisher=event_publisher,
    )


@pytest.mark.asyncio
async def test_coordinator_application_facade_preserves_standard_request_boundary() -> None:
    standard = AsyncMock(return_value={"status": "standard"})

    result = await _facade(standard_request_handler=standard).handle_request(
        {"action": "describe"}
    )

    assert result == {"status": "standard"}
    standard.assert_awaited_once_with({"action": "describe"})


@pytest.mark.asyncio
async def test_coordinator_application_facade_returns_unknown_action_error() -> None:
    result = await _facade().handle_request({"action": "invalid"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
        "action": "invalid",
    }


@pytest.mark.asyncio
async def test_coordinator_application_facade_dispatches_event_use_case() -> None:
    decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_001",
        instruction="Produce PRD",
        workflow_id="wf_001",
    )
    thinker = AsyncMock(return_value=[decision])
    event = Event.create(
        event_type=EventTypes.COORDINATOR_COMMAND,
        source_agent="chat-agent",
        payload={
            "command_id": "cmd_001",
            "intent": "new feature",
            "original_message": "new feature",
            "user_id": "u1",
            "user_name": "Alice",
        },
        trace_id="trace_001",
    )

    result = await _facade(thinker=thinker).handle_event(event)

    assert len(result) == 1
    assert result[0].event_type == EventTypes.COORDINATOR_DISPATCH
    assert result[0].metadata.trace_id == "trace_001"


@pytest.mark.asyncio
async def test_coordinator_application_facade_delegates_health_check() -> None:
    result = await _facade(scratchpad=_Scratchpad(initialized=True)).health_check()

    assert result == {
        "scratchpad": True,
        "state_store": True,
        "llm_gateway": True,
        "database": True,
    }


@pytest.mark.asyncio
async def test_coordinator_application_facade_delegates_outbox_delivery() -> None:
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = _OutboxStore(rows=[_outbox_row(event_id="evt_pending")])
    facade = _facade(outbox_store=outbox_store, event_publisher=publisher)
    event = Event.create(
        event_type=EventTypes.QA_RUN_REQUESTED,
        source_agent="coordinator",
        payload={"agent_name": "dev-agent", "level": "all"},
    )

    ok = await facade.publish_event_via_outbox(event)
    result = await facade.publish_pending_coordinator_events(limit=1)

    assert ok is True
    assert outbox_store.added == [event]
    assert outbox_store.last_limit == 1
    assert result == {"total": 1, "published": 1, "failed": 0}
    assert publisher.publish.await_count == 2
