"""Tests for the Evolution application facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.evolution.core.application_facade import (
    EvolutionApplicationFacade,
)
from shared.schemas.event import Event, EventTypes


class _Analyzer:
    def __init__(self) -> None:
        self.analyze = AsyncMock(
            return_value=[{"operation": "add_skill", "target_agent": "pjm-agent"}]
        )


class _EventFactory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="evolution-module",
            payload=payload,
            trace_id=trace_id,
        )


class _ApprovalService:
    def __init__(self) -> None:
        self.approve_for_sensitive_action = AsyncMock()
        self.reject_for_sensitive_action = AsyncMock()


class _HealthStore:
    async def is_database_ready(self) -> bool:
        return True


class _SeedStore:
    def __init__(self) -> None:
        self.seed_count = 2
        self.seeds = []

    async def seed_missing_active_skills(self, seeds) -> int:
        self.seeds = list(seeds)
        return self.seed_count


class _OutboxRow:
    event_id = "evt_pending"
    event_type = EventTypes.EVOLUTION_SKILL_PROPOSED
    source_agent = "evolution-module"
    payload = {"operation": "add_skill"}
    schema_version = "1.0"
    trace_id = "trace-evolution"
    correlation_id = None
    retry_count = 0
    created_at = datetime.now(UTC)


class _OutboxStore:
    def __init__(self, rows: list[_OutboxRow] | None = None) -> None:
        self.added: list[Event] = []
        self.rows = rows or []
        self.last_limit: int | None = None
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def add(self, event: Event) -> None:
        self.added.append(event)

    async def list_pending(self, limit: int = 100) -> list[_OutboxRow]:
        self.last_limit = limit
        return self.rows

    async def mark_published(self, event_id: str) -> None:
        self.published.append(event_id)

    async def mark_failed(self, event_id: str, error: str) -> None:
        self.failed.append((event_id, error))


async def _attach_approval(proposal: dict, **kwargs) -> dict:
    return {
        **proposal,
        "control_plane_approval_id": "appr_test",
        "trace_id": kwargs.get("trace_id"),
    }


def _facade(
    *,
    standard_request_handler=None,
    analyzer=None,
    event_bus=None,
    outbox_store=None,
    event_publisher=None,
    seed_store=None,
):
    if standard_request_handler is None:
        standard_request_handler = AsyncMock(return_value=None)
    if analyzer is None:
        analyzer = _Analyzer()
    if event_bus is None:
        event_bus = AsyncMock()
        event_bus.is_connected = True
        event_bus.connect = AsyncMock()
    if outbox_store is None:
        outbox_store = _OutboxStore()
    if event_publisher is None:
        event_publisher = AsyncMock()
        event_publisher.publish = AsyncMock(return_value=True)
    if seed_store is None:
        seed_store = _SeedStore()
    return (
        EvolutionApplicationFacade(
            standard_request_handler=standard_request_handler,
            analyzer_provider=lambda: analyzer,
            attach_proposal_approval=_attach_approval,
            event_factory=_EventFactory(),
            approval_service_provider=lambda: _ApprovalService(),
            approval_gateway_provider=lambda: None,
            collaboration_enabled_provider=lambda: False,
            health_store_provider=lambda: _HealthStore(),
            event_bus=event_bus,
            llm_gateway_provider=lambda: object(),
            seed_store_provider=lambda: seed_store,
            outbox_store_provider=lambda: outbox_store,
            event_publisher=event_publisher,
        ),
        analyzer,
        seed_store,
    )


@pytest.mark.asyncio
async def test_evolution_application_facade_preserves_standard_request_boundary() -> None:
    standard_handler = AsyncMock(return_value={"agent_id": "evolution-module"})
    facade, analyzer, _ = _facade(standard_request_handler=standard_handler)

    result = await facade.handle_request({"action": "describe"})

    assert result == {"agent_id": "evolution-module"}
    standard_handler.assert_awaited_once()
    analyzer.analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_evolution_application_facade_dispatches_request_use_case() -> None:
    facade, analyzer, _ = _facade()

    result = await facade.handle_request({"action": "trigger_analysis", "days": 14})

    assert result["proposals"][0]["control_plane_approval_id"] == "appr_test"
    analyzer.analyze.assert_awaited_once_with(14)


@pytest.mark.asyncio
async def test_evolution_application_facade_dispatches_event_use_case() -> None:
    facade, analyzer, _ = _facade()
    event = Event.create(
        event_type=EventTypes.EVOLUTION_CYCLE_TRIGGERED,
        source_agent="test",
        payload={"days": 3},
        trace_id="trace-evolution",
    )

    events = await facade.handle_event(event)

    assert len(events) == 1
    assert events[0].event_type == EventTypes.EVOLUTION_SKILL_PROPOSED
    assert events[0].metadata.trace_id == "trace-evolution"
    assert events[0].payload["control_plane_approval_id"] == "appr_test"
    analyzer.analyze.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_evolution_application_facade_delegates_health_check() -> None:
    facade, _, _ = _facade()

    result = await facade.health_check()

    assert result == {
        "database": True,
        "event_bus": True,
        "llm_gateway": True,
        "control_plane_approval_service": True,
    }


@pytest.mark.asyncio
async def test_evolution_application_facade_delegates_seed_bootstrap() -> None:
    seed_store = _SeedStore()
    facade, _, _ = _facade(seed_store=seed_store)

    result = await facade.bootstrap_seeds()

    assert result == 2
    assert seed_store.seeds


@pytest.mark.asyncio
async def test_evolution_application_facade_delegates_outbox_delivery() -> None:
    outbox_store = _OutboxStore(rows=[_OutboxRow()])
    event_publisher = AsyncMock()
    event_publisher.publish = AsyncMock(return_value=True)
    facade, _, _ = _facade(
        outbox_store=outbox_store,
        event_publisher=event_publisher,
    )
    event = Event.create(
        event_type=EventTypes.EVOLUTION_SKILL_PROPOSED,
        source_agent="evolution-module",
        payload={"operation": "add_skill"},
    )

    ok = await facade.publish_event_via_outbox(event)
    result = await facade.publish_pending_evolution_events(limit=1)

    assert ok is True
    assert outbox_store.added == [event]
    assert outbox_store.last_limit == 1
    assert outbox_store.published == [event.event_id, "evt_pending"]
    assert result == {"total": 1, "published": 1, "failed": 0}
