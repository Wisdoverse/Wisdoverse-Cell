from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.pjm_agent.core.request_use_cases import PJMRequestUseCase
from shared.core import UNKNOWN_ACTION_ERROR_CODE


def _use_case(
    *,
    config: MagicMock | None = None,
    alert: AsyncMock | None = None,
    push: AsyncMock | None = None,
    report: AsyncMock | None = None,
    decomposition: AsyncMock | None = None,
    decomposition_store: AsyncMock | None = None,
) -> PJMRequestUseCase:
    if config is None:
        config = MagicMock()
        config.members = [{"name": "Alice"}]
        config.projects = [{"name": "Project"}]
        config.rules = {"deadline": "3"}
        config.refresh = AsyncMock()

    if alert is None:
        alert = AsyncMock()
        alert.check_all = AsyncMock(return_value=[{"type": "deadline"}])

    if push is None:
        push = AsyncMock()
        push.push_alerts = AsyncMock(return_value=True)
        push.send_stale_approval_reminder = AsyncMock()

    if report is None:
        report = AsyncMock()
        report.generate_daily = AsyncMock(
            return_value={"card": {"daily": True}, "stats": {"total": 3}}
        )
        report.generate_weekly = AsyncMock(
            return_value={"card": {"weekly": True}, "stats": {"total": 5}}
        )
        report.push_card = AsyncMock()

    if decomposition is None:
        decomposition = AsyncMock()
        decomposition.retry_decompose = AsyncMock(return_value={"status": "retried"})
        decomposition.get_decompose = AsyncMock(return_value={"status": "found"})

    if decomposition_store is None:
        decomposition_store = AsyncMock()
        decomposition_store.list_stale_pending = AsyncMock(return_value=[])

    return PJMRequestUseCase(
        config=config,
        alert=alert,
        push=push,
        report=report,
        decomposition=decomposition,
        decomposition_store=decomposition_store,
    )


@pytest.mark.asyncio
async def test_config_action_returns_config_snapshot() -> None:
    result = await _use_case().handle({"action": "config"})

    assert result == {
        "members": [{"name": "Alice"}],
        "projects": [{"name": "Project"}],
        "rules": {"deadline": "3"},
    }


@pytest.mark.asyncio
async def test_alerts_and_push_alerts_actions_delegate_to_ports() -> None:
    push = AsyncMock()
    push.push_alerts = AsyncMock(return_value=True)
    push.send_stale_approval_reminder = AsyncMock()
    use_case = _use_case(push=push)

    assert await use_case.handle({"action": "alerts"}) == {
        "alerts": [{"type": "deadline"}]
    }
    assert await use_case.handle(
        {"action": "push_alerts", "alerts": [{"type": "blocked"}]}
    ) == {"status": "pushed", "count": 1}
    push.push_alerts.assert_awaited_once_with([{"type": "blocked"}])


@pytest.mark.asyncio
async def test_refresh_config_action_refreshes_config() -> None:
    config = MagicMock()
    config.members = []
    config.projects = []
    config.rules = {}
    config.refresh = AsyncMock()

    result = await _use_case(config=config).handle({"action": "refresh_config"})

    assert result == {"status": "refreshed"}
    config.refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_decomposition_actions_delegate_to_decomposition_port() -> None:
    decomposition = AsyncMock()
    decomposition.retry_decompose = AsyncMock(return_value={"status": "retried"})
    decomposition.get_decompose = AsyncMock(return_value={"status": "found"})
    use_case = _use_case(decomposition=decomposition)

    assert await use_case.handle({"action": "retry_decompose", "wp_id": 123}) == {
        "status": "retried"
    }
    assert await use_case.handle({"action": "get_decompose", "wp_id": 123}) == {
        "status": "found"
    }
    decomposition.retry_decompose.assert_awaited_once_with(123)
    decomposition.get_decompose.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_report_actions_generate_and_push_cards() -> None:
    report = AsyncMock()
    report.generate_daily = AsyncMock(
        return_value={"card": {"daily": True}, "stats": {"total": 3}}
    )
    report.generate_weekly = AsyncMock(
        return_value={"card": {"weekly": True}, "stats": {"total": 5}}
    )
    report.push_card = AsyncMock()
    use_case = _use_case(report=report)

    assert await use_case.handle({"action": "daily_report"}) == {
        "status": "sent",
        "total": 3,
    }
    assert await use_case.handle({"action": "weekly_report"}) == {
        "status": "sent",
        "total": 5,
    }
    report.push_card.assert_any_await({"daily": True})
    report.push_card.assert_any_await({"weekly": True})


@pytest.mark.asyncio
async def test_report_failure_returns_error_contract() -> None:
    report = AsyncMock()
    report.generate_daily = AsyncMock(side_effect=RuntimeError("report down"))
    report.generate_weekly = AsyncMock()
    report.push_card = AsyncMock()

    result = await _use_case(report=report).handle({"action": "daily_report"})

    assert result == {
        "error": "report_failed",
        "error_code": "report_failed",
    }


@pytest.mark.asyncio
async def test_check_stale_approvals_sends_reminders() -> None:
    push = AsyncMock()
    push.push_alerts = AsyncMock()
    push.send_stale_approval_reminder = AsyncMock()
    decomposition_store = AsyncMock()
    decomposition_store.list_stale_pending = AsyncMock(
        return_value=[
            SimpleNamespace(
                wp_id=123,
                decompose_result={"summary": "Implement API"},
            )
        ]
    )

    result = await _use_case(
        push=push,
        decomposition_store=decomposition_store,
    ).handle({"action": "check_stale_approvals"})

    assert result == {"status": "ok"}
    decomposition_store.list_stale_pending.assert_awaited_once_with(
        older_than_hours=24
    )
    push.send_stale_approval_reminder.assert_awaited_once_with(
        wp_id=123,
        subject="Implement API",
    )


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_request_result_contract() -> None:
    result = await _use_case().handle({"action": "unknown"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }
