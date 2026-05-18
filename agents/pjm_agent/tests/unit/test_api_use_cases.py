"""Tests for PJM API application use cases."""

from unittest.mock import AsyncMock

import pytest

from agents.pjm_agent.core.api_use_cases import (
    PMApiConfigFailedError,
    PMApiDecompositionForbiddenError,
    PMApiDecompositionNotFoundError,
    PMApiDecompositionRetryFailedError,
    PMApiDecompositionUnavailableError,
    PMApiReportFailedError,
    PMApiUseCase,
    PMDecompositionActionCommand,
)


@pytest.mark.asyncio
async def test_get_config_forwards_config_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {
        "members": [{"name": "Alice"}],
        "projects": [{"name": "Platform"}],
        "rules": [],
    }

    result = await PMApiUseCase(agent).get_config()

    assert result["members"] == [{"name": "Alice"}]
    agent.handle_request.assert_awaited_once_with({"action": "config"})


@pytest.mark.asyncio
async def test_get_config_wraps_agent_exception() -> None:
    agent = AsyncMock()
    agent.handle_request.side_effect = RuntimeError("bitable unavailable")

    with pytest.raises(PMApiConfigFailedError, match="bitable unavailable"):
        await PMApiUseCase(agent).get_config()


@pytest.mark.asyncio
async def test_get_alerts_counts_agent_alerts() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {
        "alerts": [
            {"type": "deadline", "task": "T1", "message": "late", "severity": "critical"}
        ]
    }

    result = await PMApiUseCase(agent).get_alerts()

    assert result["total"] == 1
    assert result["alerts"][0]["type"] == "deadline"
    agent.handle_request.assert_awaited_once_with({"action": "alerts"})


@pytest.mark.asyncio
async def test_report_action_wraps_error_result() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"error": "Traceback: secret"}

    with pytest.raises(PMApiReportFailedError, match="Traceback: secret"):
        await PMApiUseCase(agent).trigger_daily_report()
    agent.handle_request.assert_awaited_once_with({"action": "daily_report"})


@pytest.mark.asyncio
async def test_retry_decomposition_wraps_error_result() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"error": "missing record"}

    with pytest.raises(PMApiDecompositionRetryFailedError, match="missing record"):
        await PMApiUseCase(agent).retry_decomposition(123)


@pytest.mark.asyncio
async def test_get_decomposition_raises_not_found_for_empty_result() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {}

    with pytest.raises(PMApiDecompositionNotFoundError):
        await PMApiUseCase(agent).get_decomposition(123)


@pytest.mark.asyncio
async def test_approve_decomposition_maps_action_response() -> None:
    agent = AsyncMock()
    agent.approve_decomposition.return_value = {
        "subject": "Split feature",
        "story_count": 2,
        "task_count": 5,
    }

    result = await PMApiUseCase(agent).approve_decomposition(
        PMDecompositionActionCommand(wp_id=123, operator="human:pm")
    )

    assert result == {
        "success": True,
        "wp_id": 123,
        "action": "approve",
        "message": "Written to OP: 2 US, 5 Task",
        "subject": "Split feature",
        "story_count": 2,
        "task_count": 5,
    }
    agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="human:pm",
    )


@pytest.mark.asyncio
async def test_approve_decomposition_none_is_unavailable() -> None:
    agent = AsyncMock()
    agent.approve_decomposition.return_value = None

    with pytest.raises(PMApiDecompositionUnavailableError):
        await PMApiUseCase(agent).approve_decomposition(
            PMDecompositionActionCommand(wp_id=123, operator="human:pm")
        )


@pytest.mark.asyncio
async def test_approve_decomposition_error_is_forbidden() -> None:
    agent = AsyncMock()
    agent.approve_decomposition.return_value = {"error": "approval required"}

    with pytest.raises(PMApiDecompositionForbiddenError, match="approval required"):
        await PMApiUseCase(agent).approve_decomposition(
            PMDecompositionActionCommand(wp_id=123, operator="human:pm")
        )


@pytest.mark.asyncio
async def test_reject_decomposition_maps_action_response() -> None:
    agent = AsyncMock()
    agent.reject_decomposition.return_value = {"subject": "Split feature"}

    result = await PMApiUseCase(agent).reject_decomposition(
        PMDecompositionActionCommand(
            wp_id=123,
            operator="human:pm",
            reason="not ready",
        )
    )

    assert result == {
        "success": True,
        "wp_id": 123,
        "action": "reject",
        "message": "Rejected",
        "subject": "Split feature",
    }
    agent.reject_decomposition.assert_awaited_once_with(
        123,
        rejected_by="human:pm",
        reason="not ready",
    )


@pytest.mark.asyncio
async def test_reject_decomposition_none_is_unavailable() -> None:
    agent = AsyncMock()
    agent.reject_decomposition.return_value = None

    with pytest.raises(PMApiDecompositionUnavailableError):
        await PMApiUseCase(agent).reject_decomposition(
            PMDecompositionActionCommand(
                wp_id=123,
                operator="human:pm",
                reason="not ready",
            )
        )


@pytest.mark.asyncio
async def test_reject_decomposition_error_is_forbidden() -> None:
    agent = AsyncMock()
    agent.reject_decomposition.return_value = {"error": "approval required"}

    with pytest.raises(PMApiDecompositionForbiddenError, match="approval required"):
        await PMApiUseCase(agent).reject_decomposition(
            PMDecompositionActionCommand(
                wp_id=123,
                operator="human:pm",
                reason="not ready",
            )
        )
