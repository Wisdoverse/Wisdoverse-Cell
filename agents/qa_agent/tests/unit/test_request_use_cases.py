from unittest.mock import AsyncMock

import pytest

from agents.qa_agent.core.request_use_cases import QARequestUseCase
from agents.qa_agent.models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceSummary,
    QARunStats,
)
from shared.core import UNKNOWN_ACTION_ERROR_CODE


def _agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run_acceptance = AsyncMock(
        return_value=AcceptanceExecutionResult(
            success=True,
            exit_code=0,
            summary=AcceptanceSummary(
                l0_gate="PASS",
                l1_check="PASS",
                l2_report="INFO",
                total_checks=2,
                l0_failures=0,
                l1_warnings=0,
            ),
            raw_report={"summary": {"l0_gate": "PASS"}},
        )
    )
    agent.list_runs = AsyncMock(return_value=[{"id": "qa_run_1"}])
    agent.get_run = AsyncMock(return_value={"id": "qa_run_1"})
    agent.get_stats = AsyncMock(
        return_value=QARunStats(
            days=30,
            total_runs=1,
            pass_runs=1,
            warn_runs=0,
            failed_runs=0,
            l0_fail_rate=0.0,
            avg_duration_seconds=1.2,
        )
    )
    return agent


@pytest.mark.asyncio
async def test_run_action_builds_api_triggered_run_request() -> None:
    agent = _agent()

    result = await QARequestUseCase(agent).handle(
        {
            "action": "run",
            "agent_name": "dev-agent",
            "level": "l0",
            "commit_sha": "abcdef1",
            "mr_iid": 12,
            "gitlab_project_id": 34,
            "requested_by": "operator",
        }
    )

    assert result == {"summary": {"l0_gate": "PASS"}}
    run_request = agent.run_acceptance.await_args.args[0]
    assert run_request.agent_name == "dev-agent"
    assert run_request.level == "l0"
    assert run_request.commit_sha == "abcdef1"
    assert run_request.mr_iid == 12
    assert run_request.gitlab_project_id == 34
    assert run_request.trigger == "api"
    assert run_request.requested_by == "operator"


@pytest.mark.asyncio
async def test_list_runs_action_wraps_items() -> None:
    agent = _agent()

    result = await QARequestUseCase(agent).handle(
        {"action": "list_runs", "agent_name": "qa-agent", "limit": 5, "offset": 2}
    )

    assert result == {"items": [{"id": "qa_run_1"}]}
    agent.list_runs.assert_awaited_once_with(
        agent_name="qa-agent",
        limit=5,
        offset=2,
    )


@pytest.mark.asyncio
async def test_get_run_action_returns_not_found_contract() -> None:
    agent = _agent()
    agent.get_run = AsyncMock(return_value=None)

    result = await QARequestUseCase(agent).handle(
        {"action": "get_run", "run_id": "missing"}
    )

    assert result == {
        "error": "not found",
        "error_code": "qa_run_not_found",
    }
    agent.get_run.assert_awaited_once_with("missing")


@pytest.mark.asyncio
async def test_stats_action_returns_model_dump() -> None:
    agent = _agent()

    result = await QARequestUseCase(agent).handle(
        {"action": "stats", "agent_name": "qa-agent", "days": 7}
    )

    assert result["days"] == 30
    assert result["total_runs"] == 1
    agent.get_stats.assert_awaited_once_with(agent_name="qa-agent", days=7)


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_request_result_contract() -> None:
    result = await QARequestUseCase(_agent()).handle({"action": "unknown"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }
