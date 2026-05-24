"""Tests for the user-interaction application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.chat_agent.core.application_facade import (
    ChatAgentApplicationFacade,
)
from agents.chat_agent.core.event_ports import (
    ChatAgentEventOutboxStore,
)
from shared.schemas.event import Event, EventTypes


class _OutboxStore(ChatAgentEventOutboxStore):
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
    async def is_database_ready(self) -> bool:
        return True


def _outbox_row(**overrides):
    defaults = {
        "event_id": "evt_chat_01",
        "event_type": EventTypes.SYNC_TRIGGER,
        "source_agent": "chat-agent",
        "payload": {"triggered_by": "chat_tool", "scope": "full"},
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
    chat=None,
    outbox_store: _OutboxStore | None = None,
    event_bus: MagicMock | None = None,
    event_publisher: MagicMock | None = None,
    standard_request_handler: AsyncMock | None = None,
) -> ChatAgentApplicationFacade:
    event_bus = event_bus or MagicMock()
    event_bus.connect = AsyncMock()
    event_publisher = event_publisher or MagicMock()
    event_publisher.publish = AsyncMock(return_value=True)
    return ChatAgentApplicationFacade(
        agent_id="chat-agent",
        standard_request_handler=standard_request_handler or AsyncMock(return_value=None),
        chat_provider=lambda: chat,
        history_store=MagicMock(),
        health_store=_HealthStore(),
        outbox_store=outbox_store if outbox_store is not None else _OutboxStore(),
        event_bus=event_bus,
        event_publisher=event_publisher,
        dispatch_morning_tasks_command=AsyncMock(),
        collect_evening_progress_command=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_user_interaction_facade_preserves_standard_request_boundary() -> None:
    standard = AsyncMock(return_value={"status": "standard"})

    result = await _facade(standard_request_handler=standard).handle_request(
        {"action": "describe"}
    )

    assert result == {"status": "standard"}
    standard.assert_awaited_once_with({"action": "describe"})


@pytest.mark.asyncio
async def test_user_interaction_facade_dispatches_request_use_case() -> None:
    chat = MagicMock()
    chat.chat = AsyncMock(return_value="hello")

    result = await _facade(chat=chat).handle_request(
        {"action": "chat", "message": "hi", "user_id": "u1"}
    )

    assert result == {"reply": "hello"}
    chat.chat.assert_awaited_once_with(message="hi", user_id="u1")


@pytest.mark.asyncio
async def test_user_interaction_facade_dispatches_event_use_case() -> None:
    event = Event.create(
        event_type=EventTypes.COORDINATOR_RESPONSE,
        source_agent="coordinator",
        payload={"task_id": "task_1", "workflow_id": "wf_1"},
    )

    result = await _facade().handle_event(event)

    assert result == []


@pytest.mark.asyncio
async def test_user_interaction_facade_delegates_health_check() -> None:
    result = await _facade(chat=MagicMock()).health_check()

    assert result == {"database": True, "chat_service": True}


@pytest.mark.asyncio
async def test_user_interaction_facade_delegates_outbox_delivery() -> None:
    publisher = MagicMock()
    publisher.publish = AsyncMock(return_value=True)
    outbox_store = _OutboxStore(rows=[_outbox_row(event_id="evt_pending")])
    facade = _facade(outbox_store=outbox_store, event_publisher=publisher)

    ok = await facade.publish_sync_trigger(scope="openproject")
    result = await facade.publish_pending_chat_agent_events(limit=1)

    assert ok is True
    assert outbox_store.added[0].event_type == EventTypes.SYNC_TRIGGER
    assert outbox_store.added[0].payload["scope"] == "openproject"
    assert outbox_store.last_limit == 1
    assert result == {"total": 1, "published": 1, "failed": 0}
    assert publisher.publish.await_count == 2
