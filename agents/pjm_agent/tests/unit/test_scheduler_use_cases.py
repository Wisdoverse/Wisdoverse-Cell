"""Tests for PJM scheduler application use cases."""

from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.core.scheduler_use_cases import PJMSchedulerUseCase


@pytest.mark.asyncio
async def test_run_hourly_alerts_pushes_non_empty_alerts() -> None:
    agent = AsyncMock()
    alerts = [{"type": "deadline", "severity": "critical"}]
    agent.handle_request.side_effect = [
        {"alerts": alerts},
        {"status": "sent"},
    ]

    result = await PJMSchedulerUseCase(agent).run_hourly_alerts()

    assert result == {"alerts": alerts}
    assert agent.handle_request.await_args_list[0].args == ({"action": "alerts"},)
    assert agent.handle_request.await_args_list[1].args == (
        {"action": "push_alerts", "alerts": alerts},
    )


@pytest.mark.asyncio
async def test_run_hourly_alerts_skips_push_for_empty_alerts() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"alerts": []}

    result = await PJMSchedulerUseCase(agent).run_hourly_alerts()

    assert result == {"alerts": []}
    agent.handle_request.assert_awaited_once_with({"action": "alerts"})


@pytest.mark.asyncio
async def test_run_scheduled_action_forwards_action_name() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"status": "ok"}

    result = await PJMSchedulerUseCase(agent).run_scheduled_action("daily_report")

    assert result == {"status": "ok"}
    agent.handle_request.assert_awaited_once_with({"action": "daily_report"})
