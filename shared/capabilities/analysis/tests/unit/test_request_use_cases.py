from unittest.mock import AsyncMock

import pytest

from shared.capabilities.analysis.core.request_use_cases import AnalysisRequestUseCase
from shared.core import UNKNOWN_ACTION_ERROR_CODE


def _use_case(
    *,
    daily: AsyncMock | None = None,
    weekly: AsyncMock | None = None,
    milestone: AsyncMock | None = None,
) -> AnalysisRequestUseCase:
    return AnalysisRequestUseCase(
        daily=daily or AsyncMock(),
        weekly=weekly or AsyncMock(),
        milestone=milestone or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_daily_report_action_delegates_to_daily_generator() -> None:
    daily = AsyncMock()
    daily.generate = AsyncMock(return_value={"content": "daily", "summary": "ok"})

    result = await _use_case(daily=daily).handle({"action": "daily_report"})

    assert result == {"content": "daily", "summary": "ok"}
    daily.generate.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_weekly_report_action_delegates_to_weekly_generator() -> None:
    weekly = AsyncMock()
    weekly.generate = AsyncMock(return_value={"content": "weekly", "summary": "ok"})

    result = await _use_case(weekly=weekly).handle({"action": "weekly_report"})

    assert result == {"content": "weekly", "summary": "ok"}
    weekly.generate.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_milestones_action_wraps_risks() -> None:
    milestone = AsyncMock()
    milestone.check = AsyncMock(return_value=[{"severity": "critical"}])

    result = await _use_case(milestone=milestone).handle(
        {"action": "check_milestones"}
    )

    assert result == {"risks": [{"severity": "critical"}]}
    milestone.check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_request_result_contract() -> None:
    result = await _use_case().handle({"action": "unknown"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }


@pytest.mark.asyncio
async def test_missing_daily_generator_fails_explicitly() -> None:
    with pytest.raises(RuntimeError, match="daily_report_generator_not_initialized"):
        await AnalysisRequestUseCase(
            daily=None,
            weekly=AsyncMock(),
            milestone=AsyncMock(),
        ).handle({"action": "daily_report"})
