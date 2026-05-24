"""Unit tests for QA run query use cases."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agents.qa_agent.core.run_query_use_cases import QARunQueryUseCase
from agents.qa_agent.models.schemas import QARunStats
from shared.core.identifiers import AcceptanceRunId


class FakeRunStore:
    def __init__(self, run=None, stats=None):
        self.run = run
        self.stats = stats
        self.list_args = None
        self.get_id = None
        self.stats_args = None

    async def list_runs(self, *, agent_name=None, limit=20, offset=0):
        self.list_args = {
            "agent_name": agent_name,
            "limit": limit,
            "offset": offset,
        }
        return [self.run] if self.run else []

    async def get_by_id(self, run_id: AcceptanceRunId):
        self.get_id = run_id
        return self.run

    async def get_by_trigger_event_id(self, trigger_event_id: str | None):
        return None

    async def get_stats(self, *, agent_name=None, days=30):
        self.stats_args = {"agent_name": agent_name, "days": days}
        return self.stats

    async def update_notification_summary(self, run_id, notification_summary):
        return True


def _run(**overrides):
    base = {
        "id": "qa_run_1",
        "agent_name": "dev-agent",
        "commit_sha": "abc123",
        "mr_iid": 12,
        "trigger": "manual",
        "level": "all",
        "files_changed": ["agents/dev_agent/service/agent.py"],
        "l0_status": "PASS",
        "l1_status": "WARN",
        "l2_status": "INFO",
        "total_checks": 5,
        "l0_failure_count": 0,
        "l1_warning_count": 1,
        "duration_seconds": 2.5,
        "runner_exit_code": 0,
        "raw_report": {"results": [{"check": "lint", "status": "PASS"}]},
        "report_markdown": "## QA",
        "notification_summary": {"eventbus": {"sent": True}},
        "created_at": datetime(2026, 5, 1, tzinfo=UTC),
        "completed_at": datetime(2026, 5, 1, 0, 0, 2, tzinfo=UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_list_runs_maps_store_records_to_api_projection() -> None:
    store = FakeRunStore(run=_run())
    result = await QARunQueryUseCase(run_store=store).list_runs(
        agent_name="dev-agent",
        limit=10,
        offset=5,
    )

    assert store.list_args == {"agent_name": "dev-agent", "limit": 10, "offset": 5}
    assert result == [
        {
            "id": "qa_run_1",
            "run_id": "qa_run_1",
            "agent_name": "dev-agent",
            "commit_sha": "abc123",
            "mr_iid": 12,
            "trigger": "manual",
            "l0_status": "PASS",
            "l1_status": "WARN",
            "total_checks": 5,
            "duration_seconds": 2.5,
            "created_at": "2026-05-01T00:00:00+00:00",
        }
    ]


@pytest.mark.asyncio
async def test_get_run_maps_detail_projection() -> None:
    store = FakeRunStore(run=_run())
    result = await QARunQueryUseCase(run_store=store).get_run(AcceptanceRunId("qa_run_1"))

    assert store.get_id == AcceptanceRunId("qa_run_1")
    assert result is not None
    assert result["run_id"] == "qa_run_1"
    assert result["summary"]["l1_warnings"] == 1
    assert result["findings"] == [{"check": "lint", "status": "PASS"}]
    assert result["completed_at"] == "2026-05-01T00:00:02+00:00"


@pytest.mark.asyncio
async def test_get_stats_delegates_to_store() -> None:
    stats = QARunStats(
        agent_name="dev-agent",
        days=7,
        total_runs=3,
        pass_runs=2,
        warn_runs=1,
        failed_runs=0,
        l0_fail_rate=0.0,
        avg_duration_seconds=3.2,
    )
    store = FakeRunStore(stats=stats)

    result = await QARunQueryUseCase(run_store=store).get_stats(
        agent_name="dev-agent",
        days=7,
    )

    assert store.stats_args == {"agent_name": "dev-agent", "days": 7}
    assert result is stats
