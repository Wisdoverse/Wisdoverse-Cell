from unittest.mock import AsyncMock, patch

import pytest

from agents.qa_agent.core.event_use_cases import QAEventUseCase
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_code_committed_event_builds_acceptance_request() -> None:
    runner = AsyncMock()
    runner.run_acceptance = AsyncMock()
    event = Event.create(
        event_type=EventTypes.CODE_COMMITTED,
        source_agent="ci",
        payload={
            "agent_name": "pjm_agent",
            "commit_sha": "abc1234567",
            "diff_ref": "main...feature",
            "files_changed": ["agents/pjm_agent/service/agent.py"],
            "branch": "feature/qa",
            "mr_iid": 12,
            "gitlab_project_id": 34,
        },
        trace_id="trace-code",
    )

    result = await QAEventUseCase(runner=runner).handle(event)

    assert result == []
    runner.run_acceptance.assert_awaited_once()
    request = runner.run_acceptance.await_args.args[0]
    assert request.agent_name == "pjm_agent"
    assert request.level == "all"
    assert request.commit_sha == "abc1234567"
    assert request.diff_ref == "main...feature"
    assert request.files_changed == ["agents/pjm_agent/service/agent.py"]
    assert request.branch == "feature/qa"
    assert request.mr_iid == 12
    assert request.gitlab_project_id == 34
    assert request.trigger == "event"
    assert request.requested_by == "code.committed"
    assert runner.run_acceptance.await_args.kwargs == {
        "trace_id": "trace-code",
        "trigger_event_id": event.event_id,
    }


@pytest.mark.asyncio
async def test_run_requested_event_builds_acceptance_request_and_logs_instruction() -> None:
    runner = AsyncMock()
    runner.run_acceptance = AsyncMock()
    event = Event.create(
        event_type=EventTypes.QA_RUN_REQUESTED,
        source_agent="dev-agent",
        payload={
            "agent_name": "dev_agent",
            "level": "l0",
            "commit_sha": "def1234567",
            "files_changed": ["agents/dev_agent/service/agent.py"],
            "mr_iid": 22,
            "gitlab_project_id": 44,
            "requested_by": "dev-agent",
            "reason": "MR created",
            "instruction": "validate change",
            "workflow_id": "wf-qa",
        },
        trace_id="trace-qa",
    )

    with patch("agents.qa_agent.core.event_use_cases.logger") as logger:
        result = await QAEventUseCase(runner=runner).handle(event)

    assert result == []
    logger.info.assert_called_once_with(
        "coordinator_instruction_received",
        instruction="validate change",
        workflow_id="wf-qa",
    )
    request = runner.run_acceptance.await_args.args[0]
    assert request.agent_name == "dev_agent"
    assert request.level == "l0"
    assert request.commit_sha == "def1234567"
    assert request.files_changed == ["agents/dev_agent/service/agent.py"]
    assert request.mr_iid == 22
    assert request.gitlab_project_id == 44
    assert request.trigger == "event"
    assert request.requested_by == "dev-agent"
    assert request.reason == "MR created"
    assert runner.run_acceptance.await_args.kwargs == {
        "trace_id": "trace-qa",
        "trigger_event_id": event.event_id,
    }


@pytest.mark.asyncio
async def test_unknown_event_returns_empty_without_running_acceptance() -> None:
    runner = AsyncMock()
    runner.run_acceptance = AsyncMock()

    result = await QAEventUseCase(runner=runner).handle(
        Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={},
        )
    )

    assert result == []
    runner.run_acceptance.assert_not_awaited()
