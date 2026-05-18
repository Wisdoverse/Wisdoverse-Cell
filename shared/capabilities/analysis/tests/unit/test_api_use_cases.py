"""Tests for Analysis API application use cases."""

from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.api_use_cases import (
    AnalysisApiDailyReportFailedError,
    AnalysisApiRiskCheckFailedError,
    AnalysisApiUseCase,
    AnalysisApiWeeklyReportFailedError,
)


@pytest.mark.asyncio
async def test_generate_daily_report_forwards_daily_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"status": "ok", "content": "daily"}

    result = await AnalysisApiUseCase(agent).generate_daily_report()

    assert result["content"] == "daily"
    agent.handle_request.assert_awaited_once_with({"action": "daily_report"})


@pytest.mark.asyncio
async def test_generate_daily_report_wraps_agent_exception() -> None:
    agent = AsyncMock()
    agent.handle_request.side_effect = RuntimeError("bitable unavailable")

    with pytest.raises(
        AnalysisApiDailyReportFailedError,
        match="bitable unavailable",
    ):
        await AnalysisApiUseCase(agent).generate_daily_report()


@pytest.mark.asyncio
async def test_generate_weekly_report_forwards_weekly_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"status": "ok", "content": "weekly"}

    result = await AnalysisApiUseCase(agent).generate_weekly_report()

    assert result["content"] == "weekly"
    agent.handle_request.assert_awaited_once_with({"action": "weekly_report"})


@pytest.mark.asyncio
async def test_generate_weekly_report_wraps_agent_exception() -> None:
    agent = AsyncMock()
    agent.handle_request.side_effect = RuntimeError("weekly failed")

    with pytest.raises(AnalysisApiWeeklyReportFailedError, match="weekly failed"):
        await AnalysisApiUseCase(agent).generate_weekly_report()


@pytest.mark.asyncio
async def test_check_risks_counts_agent_risks() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {
        "risks": [
            {"feature": "#100", "risk_level": "critical", "message": "blocked"},
        ]
    }

    result = await AnalysisApiUseCase(agent).check_risks()

    assert result["total"] == 1
    assert result["risks"][0]["feature"] == "#100"
    agent.handle_request.assert_awaited_once_with({"action": "check_milestones"})


@pytest.mark.asyncio
async def test_check_risks_wraps_agent_exception() -> None:
    agent = AsyncMock()
    agent.handle_request.side_effect = RuntimeError("risk source unavailable")

    with pytest.raises(
        AnalysisApiRiskCheckFailedError,
        match="risk source unavailable",
    ):
        await AnalysisApiUseCase(agent).check_risks()
