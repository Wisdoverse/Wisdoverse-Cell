from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.core.config import DevCoreConfig
from agents.dev_agent.core.domain.lifecycle.task_lifecycle import FAILED, PLANNING
from agents.dev_agent.core.result_collector import ResultCollector
from agents.dev_agent.models.schemas import VALID_TRANSITIONS
from shared.schemas.event import EventTypes


def test_executing_to_security_scanning():
    assert "security_scanning" in VALID_TRANSITIONS["executing"]


def test_security_scanning_to_mr_creating():
    assert "mr_creating" in VALID_TRANSITIONS["security_scanning"]


def test_mr_created_to_qa_triggered():
    assert "qa_triggered" in VALID_TRANSITIONS["mr_created"]


def test_reviewing_to_completed():
    assert "completed" in VALID_TRANSITIONS["reviewing"]


def test_reviewing_to_failed():
    assert "failed" in VALID_TRANSITIONS["reviewing"]


def test_failed_can_retry():
    assert "planning" in VALID_TRANSITIONS["failed"]


def test_completed_is_terminal():
    assert VALID_TRANSITIONS["completed"] == set()


@pytest.mark.asyncio
async def test_result_collector_uses_injected_gitlab_project_id_for_qa_event():
    task = SimpleNamespace(
        id="dev-1",
        wp_id=123,
        task_title="Dev Agent task",
        risk_level="MEDIUM",
    )
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    gitlab = AsyncMock()
    gitlab.check_existing_mr = AsyncMock(return_value=None)
    gitlab.create_mr = AsyncMock(return_value={"iid": 7, "web_url": "https://mr/7"})
    scanner = AsyncMock()
    scanner.scan = AsyncMock(return_value=MagicMock(passed=True, issues=[]))
    notifier = AsyncMock()

    collector = ResultCollector(
        repo=repo,
        log_repo=AsyncMock(),
        gitlab=gitlab,
        notifier=notifier,
        security_scanner=scanner,
        config=DevCoreConfig.from_values(gitlab_project_id=42),
    )

    events = await collector.handle_completion(task, {"status": "completed"})

    qa_event = next(event for event in events if event.event_type == EventTypes.QA_RUN_REQUESTED)
    assert qa_event.payload["gitlab_project_id"] == 42


@pytest.mark.asyncio
async def test_completion_recovers_trace_from_persisted_workflow_log():
    task = SimpleNamespace(
        id="dev-traced",
        wp_id=123,
        task_title="Dev Agent task",
        risk_level="MEDIUM",
    )
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    log_repo = AsyncMock()
    log_repo.get_by_task_id = AsyncMock(
        return_value=SimpleNamespace(
            workflow_json={"metadata": {"trace_id": "trace-from-pjm"}}
        )
    )
    gitlab = AsyncMock()
    gitlab.check_existing_mr = AsyncMock(return_value=None)
    gitlab.create_mr = AsyncMock(return_value={"iid": 17, "web_url": "https://mr/17"})
    scanner = AsyncMock()
    scanner.scan = AsyncMock(return_value=MagicMock(passed=True, issues=[]))
    notifier = AsyncMock()
    collector = ResultCollector(
        repo=repo,
        log_repo=log_repo,
        gitlab=gitlab,
        notifier=notifier,
        security_scanner=scanner,
    )

    events = await collector.handle_completion(task, {"status": "completed"})

    by_type = {event.event_type: event for event in events}
    for event_type in (EventTypes.QA_RUN_REQUESTED, EventTypes.DEV_MR_CREATED):
        assert by_type[event_type].metadata.trace_id == "trace-from-pjm"
    log_repo.get_by_task_id.assert_awaited_once_with("dev-traced")


@pytest.mark.asyncio
async def test_qa_result_recover_trace_for_completed_and_failed_events():
    log_repo = AsyncMock()
    log_repo.get_by_task_id = AsyncMock(
        return_value=SimpleNamespace(
            workflow_json={"metadata": {"trace_id": "trace-from-pjm"}}
        )
    )
    notifier = AsyncMock()
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    collector = ResultCollector(
        repo=repo,
        log_repo=log_repo,
        gitlab=AsyncMock(),
        notifier=notifier,
    )

    completed = await collector.handle_qa_result(
        SimpleNamespace(
            id="dev-completed",
            wp_id=123,
            mr_url="https://mr/17",
            retry_count=0,
            created_at=None,
        ),
        {"summary": {"l0_gate": "PASS"}},
    )
    failed = await collector.handle_qa_result(
        SimpleNamespace(
            id="dev-failed",
            wp_id=124,
            mr_url="https://mr/18",
            retry_count=1,
            created_at=None,
        ),
        {"summary": {"l0_gate": "FAIL"}},
    )

    assert completed[0].event_type == EventTypes.DEV_TASK_COMPLETED
    assert completed[0].metadata.trace_id == "trace-from-pjm"
    assert failed[0].event_type == EventTypes.DEV_TASK_FAILED
    assert failed[0].metadata.trace_id == "trace-from-pjm"
    assert log_repo.get_by_task_id.await_count == 2


@pytest.mark.asyncio
async def test_result_collector_uses_shared_qa_gate_contract_for_retry():
    task = SimpleNamespace(
        id="dev-1",
        wp_id=123,
        mr_url="https://mr/7",
        retry_count=0,
        created_at=None,
    )
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    notifier = AsyncMock()
    collector = ResultCollector(
        repo=repo,
        log_repo=AsyncMock(),
        gitlab=AsyncMock(),
        notifier=notifier,
    )

    events = await collector.handle_qa_result(
        task,
        {"summary": {"l0_gate": "ERROR"}},
    )

    assert events == []
    repo.update_status.assert_any_await(
        "dev-1",
        FAILED,
        error_message="QA L0 failed",
        failed_step="qa",
    )
    repo.update_status.assert_any_await("dev-1", PLANNING, retry_count=1)
    notifier.notify_task_completed.assert_not_awaited()
