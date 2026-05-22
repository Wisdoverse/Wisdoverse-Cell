"""Tests for the PJM application facade."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.pjm_agent.core.application_facade import PJMApplicationFacade
from agents.pjm_agent.core.event_use_cases import NoopPJMMetrics
from shared.schemas.event import Event, EventTypes


def _event_factory() -> MagicMock:
    factory = MagicMock()
    factory.agent_id = "pjm-agent"

    def create_event(
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent=factory.agent_id,
            payload=payload,
            trace_id=trace_id,
        )

    factory.create_event.side_effect = create_event
    return factory


def _facade(
    *,
    standard_request_handler: AsyncMock | None = None,
    config: MagicMock | None = None,
    alert: AsyncMock | None = None,
    push: AsyncMock | None = None,
    report: AsyncMock | None = None,
    decomposition: AsyncMock | None = None,
    decomposition_store: AsyncMock | None = None,
    alert_log_store: AsyncMock | None = None,
    health_store: AsyncMock | None = None,
    event_factory: MagicMock | None = None,
) -> PJMApplicationFacade:
    config = config or MagicMock(members=[], projects=[], rules={})
    config.refresh = AsyncMock()
    alert = alert or AsyncMock()
    alert.check_all = AsyncMock(return_value=[])
    push = push or AsyncMock()
    push.push_alerts = AsyncMock(return_value=True)
    push.push_risks = AsyncMock(return_value=True)
    report = report or AsyncMock()
    decomposition = decomposition or AsyncMock()
    decomposition_store = decomposition_store or AsyncMock()
    alert_log_store = alert_log_store or AsyncMock()
    health_store = health_store or AsyncMock()
    return PJMApplicationFacade(
        standard_request_handler=standard_request_handler or AsyncMock(return_value=None),
        config_provider=lambda: config,
        alert_provider=lambda: alert,
        push_provider=lambda: push,
        report_provider=lambda: report,
        decomposition_provider=lambda: decomposition,
        decomposition_store_provider=lambda: decomposition_store,
        alert_log_store=alert_log_store,
        health_store=health_store,
        event_factory=event_factory or _event_factory(),
        metrics=NoopPJMMetrics(),
    )


@pytest.mark.asyncio
async def test_pjm_application_facade_dispatches_event_use_case() -> None:
    alert = AsyncMock()
    alert.check_all = AsyncMock(return_value=[])
    event = Event.create(
        event_type=EventTypes.SYNC_COMPLETED,
        source_agent="sync-module",
        payload={},
    )

    result = await _facade(alert=alert).handle_event(event)

    assert result == []
    alert.check_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_pjm_application_facade_dispatches_request_use_case() -> None:
    config = MagicMock(
        members=[{"name": "Alice"}],
        projects=[{"name": "P1"}],
        rules={"deadline": "3"},
    )
    config.refresh = AsyncMock()

    result = await _facade(config=config).handle_request({"action": "config"})

    assert result == {
        "members": [{"name": "Alice"}],
        "projects": [{"name": "P1"}],
        "rules": {"deadline": "3"},
    }


@pytest.mark.asyncio
async def test_pjm_application_facade_preserves_standard_request_boundary() -> None:
    standard = AsyncMock(return_value={"status": "standard"})

    result = await _facade(standard_request_handler=standard).handle_request(
        {"type": "health"}
    )

    assert result == {"status": "standard"}
    standard.assert_awaited_once_with({"type": "health"})


@pytest.mark.asyncio
async def test_pjm_application_facade_delegates_health_check() -> None:
    config = MagicMock(members=["pm"], projects=[], rules={})
    health_store = AsyncMock()
    health_store.is_database_ready = AsyncMock(return_value=True)

    result = await _facade(config=config, health_store=health_store).health_check()

    assert result == {"database": True, "config_loaded": True}
    health_store.is_database_ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_pjm_application_facade_delegates_outbox_delivery() -> None:
    decomposition = AsyncMock()
    decomposition.publish_pending_pjm_events = AsyncMock(return_value={"published": 2})
    event = Event.create(
        event_type=EventTypes.PM_ALERT_TRIGGERED,
        source_agent="pjm-agent",
        payload={},
    )

    facade = _facade(decomposition=decomposition)

    assert await facade.publish_pending_pjm_events(limit=5) == {"published": 2}
    await facade.publish_event_via_outbox(event, wp_id=123)

    decomposition.publish_pending_pjm_events.assert_awaited_once_with(limit=5)
    decomposition.publish_event_via_outbox.assert_awaited_once_with(event, wp_id=123)


@pytest.mark.asyncio
async def test_pjm_application_facade_checks_approval_timeouts() -> None:
    decomposition = AsyncMock()
    decomposition.publish_event_via_outbox = AsyncMock()
    decomposition_store = AsyncMock()
    decomposition_store.list_stale_pending = AsyncMock(
        return_value=[
            MagicMock(
                id="dec_001",
                created_at=datetime.now(UTC) - timedelta(hours=25),
            )
        ]
    )

    await _facade(
        decomposition=decomposition,
        decomposition_store=decomposition_store,
    ).check_approval_timeouts()

    decomposition_store.list_stale_pending.assert_awaited_once_with(
        older_than_hours=24
    )
    published = decomposition.publish_event_via_outbox.await_args.args[0]
    assert published.event_type == EventTypes.PM_APPROVAL_TIMEOUT
    assert published.source_agent == "pjm-agent"
    assert published.payload["record_id"] == "dec_001"


@pytest.mark.asyncio
async def test_pjm_application_facade_delegates_approval_actions() -> None:
    decomposition = AsyncMock()
    decomposition.approve_decomposition = AsyncMock(return_value={"status": "approved"})
    decomposition.reject_decomposition = AsyncMock(return_value={"status": "rejected"})

    facade = _facade(decomposition=decomposition)

    assert await facade.approve_decomposition(123, "human:pm") == {
        "status": "approved"
    }
    assert await facade.reject_decomposition(123, "human:pm", reason="split") == {
        "status": "rejected"
    }
    decomposition.approve_decomposition.assert_awaited_once_with(123, "human:pm")
    decomposition.reject_decomposition.assert_awaited_once_with(
        123,
        "human:pm",
        reason="split",
    )
