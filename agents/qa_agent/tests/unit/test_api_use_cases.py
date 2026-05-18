"""Tests for QA API application use cases."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agents.qa_agent.core.api_use_cases import (
    QAApiListRunsFailedError,
    QAApiRunFailedError,
    QAApiRunNotFoundError,
    QAApiUseCase,
    QAListRunsQuery,
    QAStatsQuery,
    QATriggerRunCommand,
)
from agents.qa_agent.models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceSummary,
    QACheckAggregate,
    QARunStats,
)


@pytest.mark.asyncio
async def test_trigger_run_builds_manual_request_and_maps_status() -> None:
    agent = AsyncMock()
    agent.run_acceptance.return_value = AcceptanceExecutionResult(
        success=True,
        exit_code=0,
        summary=AcceptanceSummary(
            l0_gate="PASS",
            l1_check="PASS",
            total_checks=3,
        ),
        duration_seconds=1.25,
        run_id="qa_run_1",
        notification_summary={"feishu": {"sent": True}},
    )

    result = await QAApiUseCase(agent).trigger_run(
        QATriggerRunCommand(
            agent_name="pjm_agent",
            level="all",
            commit_sha=None,
            files_changed=["agents/pjm_agent/service/agent.py"],
            mr_iid=None,
            gitlab_project_id=None,
            requested_by="tester",
            reason="manual check",
        )
    )

    request = agent.run_acceptance.call_args.args[0]
    assert request.trigger == "manual"
    assert request.requested_by == "tester"
    assert request.reason == "manual check"
    assert result["run_id"] == "qa_run_1"
    assert result["status"] == "passed"
    assert result["notification_summary"] == {"feishu": {"sent": True}}


@pytest.mark.asyncio
async def test_trigger_run_wraps_agent_failure() -> None:
    agent = AsyncMock()
    agent.run_acceptance.side_effect = RuntimeError("runner crashed")

    with pytest.raises(QAApiRunFailedError, match="runner crashed"):
        await QAApiUseCase(agent).trigger_run(
            QATriggerRunCommand(
                agent_name="pjm_agent",
                level="all",
                commit_sha=None,
                files_changed=[],
                mr_iid=None,
                gitlab_project_id=None,
                requested_by="tester",
                reason=None,
            )
        )


@pytest.mark.asyncio
async def test_list_runs_maps_repository_rows() -> None:
    created_at = datetime.now(UTC)
    agent = AsyncMock()
    agent.list_runs.return_value = [
        {
            "id": "run_1",
            "agent_name": "pjm_agent",
            "commit_sha": "abcdef1",
            "mr_iid": 12,
            "trigger": "manual",
            "l0_status": "PASS",
            "l1_status": "WARN",
            "total_checks": 4,
            "duration_seconds": 2.0,
            "created_at": created_at,
        }
    ]

    result = await QAApiUseCase(agent).list_runs(
        QAListRunsQuery(agent_name="pjm_agent", limit=20, offset=0)
    )

    assert result["total"] == 1
    assert result["items"][0]["run_id"] == "run_1"
    assert result["items"][0]["created_at"] == created_at


@pytest.mark.asyncio
async def test_list_runs_wraps_failures() -> None:
    agent = AsyncMock()
    agent.list_runs.side_effect = RuntimeError("db down")

    with pytest.raises(QAApiListRunsFailedError, match="db down"):
        await QAApiUseCase(agent).list_runs(
            QAListRunsQuery(agent_name=None, limit=20, offset=0)
        )


@pytest.mark.asyncio
async def test_get_run_detail_raises_not_found() -> None:
    agent = AsyncMock()
    agent.get_run.return_value = None

    with pytest.raises(QAApiRunNotFoundError):
        await QAApiUseCase(agent).get_run_detail("missing")


@pytest.mark.asyncio
async def test_get_stats_maps_stats_model() -> None:
    agent = AsyncMock()
    agent.get_stats.return_value = QARunStats(
        agent_name="pjm_agent",
        days=7,
        total_runs=10,
        pass_runs=8,
        warn_runs=1,
        failed_runs=1,
        l0_fail_rate=0.1,
        avg_duration_seconds=1.2,
        top_l0_failures=[QACheckAggregate(check="security", count=1)],
        top_l1_warnings=[],
    )

    result = await QAApiUseCase(agent).get_stats(
        QAStatsQuery(agent_name="pjm_agent", days=7)
    )

    assert result["total_runs"] == 10
    assert result["top_l0_failures"][0].check == "security"
