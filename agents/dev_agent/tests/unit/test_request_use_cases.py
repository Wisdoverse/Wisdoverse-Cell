from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.dev_agent.core.request_use_cases import DevRequestUseCase
from shared.control_plane import ApprovalRequiredError


def _workflow_json() -> dict:
    return {
        "name": "dev-task",
        "description": "Implement task",
        "nodes": [
            {
                "name": "step1",
                "type": "agent_task",
                "dependsOn": [],
                "config": {},
            }
        ],
    }


def _task(**overrides):
    data = {
        "id": "dev-1",
        "wp_id": 123,
        "status": "executing",
        "risk_level": "MEDIUM",
        "workflow_id": "wf-1",
        "mr_url": "https://gitlab.example/mr/1",
        "retry_count": 0,
        "error_message": None,
        "failed_step": None,
        "created_at": datetime(2026, 5, 18, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _use_case(
    *,
    repo: AsyncMock | None = None,
    log_repo: AsyncMock | None = None,
    approval_gate: AsyncMock | None = None,
    workflow_executor: AsyncMock | None = None,
) -> DevRequestUseCase:
    if repo is None:
        repo = AsyncMock()
    if log_repo is None:
        log_repo = AsyncMock()
    if approval_gate is None:
        approval_gate = AsyncMock()
        approval_gate.approve_for_sensitive_action = AsyncMock(
            return_value=SimpleNamespace(approval_id="appr-1")
        )
    if workflow_executor is None:
        workflow_executor = AsyncMock()
        workflow_executor.execute_workflow = AsyncMock(return_value=[])

    return DevRequestUseCase(
        repo=repo,
        log_repo=log_repo,
        approval_gate=approval_gate,
        workflow_executor=workflow_executor,
    )


@pytest.mark.asyncio
async def test_get_task_status_returns_serialized_task() -> None:
    repo = AsyncMock()
    repo.get_by_wp_id = AsyncMock(return_value=_task())

    result = await _use_case(repo=repo).handle(
        {"action": "get_task_status", "wp_id": 123}
    )

    assert result == {
        "wp_id": 123,
        "status": "executing",
        "risk_level": "MEDIUM",
        "workflow_id": "wf-1",
        "mr_url": "https://gitlab.example/mr/1",
        "retry_count": 0,
        "error_message": None,
        "created_at": "2026-05-18 00:00:00+00:00",
    }
    repo.get_by_wp_id.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_get_task_status_validates_wp_id() -> None:
    result = await _use_case().handle({"action": "get_task_status"})

    assert result == {"error": "wp_id required", "error_code": "wp_id_required"}


@pytest.mark.asyncio
async def test_list_actions_return_workflow_summaries() -> None:
    repo = AsyncMock()
    repo.list_active_tasks = AsyncMock(
        return_value=[_task(status="executing", risk_level="HIGH")]
    )
    repo.list_failed_tasks = AsyncMock(
        return_value=[
            _task(
                status="failed",
                error_message="boom",
                failed_step="test",
                retry_count=2,
            )
        ]
    )
    use_case = _use_case(repo=repo)

    active = await use_case.handle({"action": "list_active_workflows"})
    failed = await use_case.handle({"action": "list_failed"})

    assert active == {
        "workflows": [
            {
                "wp_id": 123,
                "status": "executing",
                "workflow_id": "wf-1",
                "risk_level": "HIGH",
            }
        ]
    }
    assert failed == {
        "workflows": [
            {
                "wp_id": 123,
                "status": "failed",
                "error_message": "boom",
                "failed_step": "test",
                "retry_count": 2,
            }
        ]
    }


@pytest.mark.asyncio
async def test_retry_task_moves_failed_task_to_planning() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=_task(status="failed", retry_count=2))
    repo.update_status = AsyncMock(return_value=True)

    result = await _use_case(repo=repo).handle(
        {"action": "retry_task", "task_id": "dev-1"}
    )

    assert result == {"success": True, "task_id": "dev-1"}
    repo.update_status.assert_awaited_once_with(
        "dev-1",
        "planning",
        retry_count=3,
    )


@pytest.mark.asyncio
async def test_cancel_workflow_marks_task_failed() -> None:
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)

    result = await _use_case(repo=repo).handle(
        {"action": "cancel_workflow", "task_id": "dev-1"}
    )

    assert result == {"success": True}
    repo.update_status.assert_awaited_once_with(
        "dev-1",
        "failed",
        error_message="Manually cancelled",
    )


@pytest.mark.asyncio
async def test_approve_workflow_requires_human_resolver_for_control_plane_id() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=_task(status="awaiting_approval"))
    log_repo = AsyncMock()
    log_repo.get_by_task_id = AsyncMock(
        return_value=SimpleNamespace(
            workflow_json={
                **_workflow_json(),
                "control_plane_approval_id": "appr-1",
            }
        )
    )
    approval_gate = AsyncMock()
    approval_gate.approve_for_sensitive_action = AsyncMock()

    result = await _use_case(
        repo=repo,
        log_repo=log_repo,
        approval_gate=approval_gate,
    ).handle({"action": "approve_workflow", "task_id": "dev-1"})

    assert result == {
        "error": "approved_by required for control-plane approval",
        "error_code": "control_plane_approval_resolver_required",
        "task_id": "dev-1",
        "control_plane_approval_id": "appr-1",
    }
    approval_gate.approve_for_sensitive_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_workflow_resolves_approval_and_executes_plan() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=_task(status="awaiting_approval"))
    log_repo = AsyncMock()
    log_repo.get_by_task_id = AsyncMock(
        return_value=SimpleNamespace(
            workflow_json={
                **_workflow_json(),
                "control_plane_approval_id": "appr-1",
            }
        )
    )
    approval_gate = AsyncMock()
    approval_gate.approve_for_sensitive_action = AsyncMock(
        return_value=SimpleNamespace(approval_id="appr-1")
    )
    workflow_executor = AsyncMock()
    workflow_executor.execute_workflow = AsyncMock(return_value=[object()])

    result = await _use_case(
        repo=repo,
        log_repo=log_repo,
        approval_gate=approval_gate,
        workflow_executor=workflow_executor,
    ).handle(
        {
            "action": "approve_workflow",
            "task_id": "dev-1",
            "approved_by": "human:lead",
        }
    )

    assert result == {
        "success": True,
        "task_id": "dev-1",
        "workflow_started": True,
        "control_plane_approval_id": "appr-1",
    }
    approval_gate.approve_for_sensitive_action.assert_awaited_once_with(
        "appr-1",
        resolved_by="human:lead",
    )
    workflow_executor.execute_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_workflow_handles_control_plane_approval_required() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=_task(status="awaiting_approval"))
    log_repo = AsyncMock()
    log_repo.get_by_task_id = AsyncMock(
        return_value=SimpleNamespace(workflow_json=_workflow_json())
    )
    approval_gate = AsyncMock()
    approval_gate.approve_for_sensitive_action = AsyncMock(
        side_effect=ApprovalRequiredError("approval needed")
    )

    result = await _use_case(
        repo=repo,
        log_repo=log_repo,
        approval_gate=approval_gate,
    ).handle({"action": "approve_workflow", "task_id": "dev-1"})

    assert result == {
        "error": "approval needed",
        "error_code": "control_plane_approval_required",
        "task_id": "dev-1",
    }


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_error_contract() -> None:
    result = await _use_case().handle({"action": "missing"})

    assert result == {
        "error": "Unknown action: missing",
        "error_code": "unknown_action",
        "action": "missing",
    }
