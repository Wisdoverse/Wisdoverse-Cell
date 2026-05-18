from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.pjm_agent.core.event_use_cases import PJMEventUseCase
from shared.schemas.event import Event, EventTypes


class _Factory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="pjm-agent",
            payload=payload,
            trace_id=trace_id,
        )


def _use_case(
    *,
    config: SimpleNamespace | None = None,
    alert: SimpleNamespace | None = None,
    push: SimpleNamespace | None = None,
    alert_log_store: SimpleNamespace | None = None,
    decomposition: SimpleNamespace | None = None,
    metrics: MagicMock | None = None,
) -> PJMEventUseCase:
    if config is None:
        config = SimpleNamespace(members=[{"name": "Alice"}], projects=[{"name": "P1"}])
    if alert is None:
        alert = SimpleNamespace(check_all=AsyncMock(return_value=[]))
    if push is None:
        push = SimpleNamespace(
            push_alerts=AsyncMock(return_value=True),
            push_risks=AsyncMock(return_value=True),
        )
    if alert_log_store is None:
        alert_log_store = SimpleNamespace(record_alerts=AsyncMock())
    if decomposition is None:
        decomposition = SimpleNamespace(
            handle_decompose=AsyncMock(return_value=[]),
            publish_event_via_outbox=AsyncMock(),
        )
    if metrics is None:
        metrics = MagicMock()
        metrics.record_alert_triggered = MagicMock()

    return PJMEventUseCase(
        agent_id="pjm-agent",
        config=config,
        alert=alert,
        push=push,
        alert_log_store=alert_log_store,
        decomposition=decomposition,
        event_factory=_Factory(),
        metrics=metrics,
    )


@pytest.mark.asyncio
async def test_sync_completed_pushes_logs_metrics_and_emits_alert_event() -> None:
    alerts = [{"type": "deadline", "severity": "critical", "message": "late"}]
    alert = SimpleNamespace(check_all=AsyncMock(return_value=alerts))
    push = SimpleNamespace(
        push_alerts=AsyncMock(return_value=True),
        push_risks=AsyncMock(),
    )
    alert_log_store = SimpleNamespace(record_alerts=AsyncMock())
    metrics = MagicMock()
    metrics.record_alert_triggered = MagicMock()

    result = await _use_case(
        alert=alert,
        push=push,
        alert_log_store=alert_log_store,
        metrics=metrics,
    ).handle(
        Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-module",
            payload={"synced": 3},
            trace_id="trace-pjm",
        )
    )

    alert.check_all.assert_awaited_once_with()
    push.push_alerts.assert_awaited_once_with(alerts)
    alert_log_store.record_alerts.assert_awaited_once_with(alerts)
    metrics.record_alert_triggered.assert_called_once_with(
        alert_type="deadline",
        severity="critical",
    )
    assert len(result) == 1
    assert result[0].event_type == EventTypes.PM_ALERT_TRIGGERED
    assert result[0].source_agent == "pjm-agent"
    assert result[0].metadata.trace_id == "trace-pjm"
    assert result[0].payload["alert_count"] == 1
    assert result[0].payload["push_ok"] is True


@pytest.mark.asyncio
async def test_sync_completed_without_alerts_returns_no_events() -> None:
    alert = SimpleNamespace(check_all=AsyncMock(return_value=[]))
    push = SimpleNamespace(push_alerts=AsyncMock(), push_risks=AsyncMock())
    alert_log_store = SimpleNamespace(record_alerts=AsyncMock())

    result = await _use_case(
        alert=alert,
        push=push,
        alert_log_store=alert_log_store,
    ).handle(
        Event.create(
            event_type=EventTypes.SYNC_COMPLETED,
            source_agent="sync-module",
            payload={},
        )
    )

    assert result == []
    push.push_alerts.assert_not_awaited()
    alert_log_store.record_alerts.assert_not_awaited()


@pytest.mark.asyncio
async def test_risk_detected_pushes_risks_without_emitting_events() -> None:
    risks = [{"type": "blocked", "message": "Dependency blocked"}]
    push = SimpleNamespace(
        push_alerts=AsyncMock(),
        push_risks=AsyncMock(return_value=True),
    )

    result = await _use_case(push=push).handle(
        Event.create(
            event_type=EventTypes.ANALYSIS_RISK_DETECTED,
            source_agent="analysis-module",
            payload={"risks": risks},
        )
    )

    assert result == []
    push.push_risks.assert_awaited_once_with(risks)


@pytest.mark.asyncio
async def test_chat_query_returns_pm_response_event() -> None:
    alert = SimpleNamespace(
        check_all=AsyncMock(
            return_value=[{"type": "deadline", "severity": "warning", "message": "soon"}]
        )
    )

    result = await _use_case(alert=alert).handle(
        Event.create(
            event_type=EventTypes.CHAT_PM_QUERY,
            source_agent="chat-agent",
            payload={"user_id": "user-001", "query": "status"},
            trace_id="trace-chat",
        )
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.CHAT_PM_RESPONSE
    assert result[0].metadata.trace_id == "trace-chat"
    assert result[0].payload["user_id"] == "user-001"
    assert result[0].payload["response"]["config_summary"] == {
        "members": 1,
        "projects": 1,
    }
    assert result[0].payload["response"]["active_alerts"] == 1


@pytest.mark.asyncio
async def test_chat_query_failure_returns_sanitized_error_response() -> None:
    alert = SimpleNamespace(check_all=AsyncMock(side_effect=RuntimeError("db down")))

    result = await _use_case(alert=alert).handle(
        Event.create(
            event_type=EventTypes.CHAT_PM_QUERY,
            source_agent="chat-agent",
            payload={"user_id": "user-001"},
            trace_id="trace-chat",
        )
    )

    assert result[0].payload["response"] == {
        "error": "Failed to retrieve PM status: RuntimeError",
        "error_code": "pm_chat_query_failed",
    }


@pytest.mark.asyncio
async def test_decompose_failure_publishes_failed_event_via_outbox() -> None:
    decomposition = SimpleNamespace(
        handle_decompose=AsyncMock(side_effect=RuntimeError("decompose unavailable")),
        publish_event_via_outbox=AsyncMock(),
    )

    result = await _use_case(decomposition=decomposition).handle(
        Event.create(
            event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            source_agent="sync-module",
            payload={"title": "Login flow"},
            trace_id="trace-decompose",
        )
    )

    assert result == []
    published = decomposition.publish_event_via_outbox.await_args.args[0]
    assert published.event_type == EventTypes.PM_DECOMPOSITION_FAILED
    assert published.source_agent == "pjm-agent"
    assert published.metadata.trace_id == "trace-decompose"
    assert published.payload["requirement_title"] == "Login flow"


@pytest.mark.asyncio
async def test_coordinator_dispatch_logs_only_targeted_messages() -> None:
    event = Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": "pjm-agent",
            "task_id": "task-1",
            "workflow_id": "wf-1",
            "instruction": "prepare",
        },
    )

    with patch("agents.pjm_agent.core.event_use_cases.logger") as logger:
        result = await _use_case().handle(event)

    assert result == []
    logger.info.assert_called_once_with(
        "coordinator_dispatch_received",
        task_id="task-1",
        workflow_id="wf-1",
        instruction="prepare",
    )


@pytest.mark.asyncio
async def test_unknown_event_returns_no_events() -> None:
    result = await _use_case().handle(
        Event.create(
            event_type="unknown.event",
            source_agent="other",
            payload={},
        )
    )

    assert result == []
