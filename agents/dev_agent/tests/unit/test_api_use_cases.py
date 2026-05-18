"""Tests for Dev API application use cases."""

from unittest.mock import AsyncMock

import pytest

from agents.dev_agent.core.api_use_cases import (
    DevApiUseCase,
    DevWorkflowApprovalCommand,
)


@pytest.mark.asyncio
async def test_list_tasks_forwards_active_workflow_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"workflows": []}

    result = await DevApiUseCase(agent).list_tasks()

    assert result == {"workflows": []}
    agent.handle_request.assert_awaited_once_with({"action": "list_active_workflows"})


@pytest.mark.asyncio
async def test_list_failed_tasks_forwards_failed_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"workflows": []}

    result = await DevApiUseCase(agent).list_failed_tasks()

    assert result == {"workflows": []}
    agent.handle_request.assert_awaited_once_with({"action": "list_failed"})


@pytest.mark.asyncio
async def test_get_task_status_forwards_wp_id() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"wp_id": 123, "status": "running"}

    result = await DevApiUseCase(agent).get_task_status(123)

    assert result["status"] == "running"
    agent.handle_request.assert_awaited_once_with(
        {"action": "get_task_status", "wp_id": 123}
    )


@pytest.mark.asyncio
async def test_retry_task_forwards_task_id() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"success": True}

    result = await DevApiUseCase(agent).retry_task("dev-001")

    assert result == {"success": True}
    agent.handle_request.assert_awaited_once_with(
        {"action": "retry_task", "task_id": "dev-001"}
    )


@pytest.mark.asyncio
async def test_cancel_workflow_forwards_task_id() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"success": True}

    result = await DevApiUseCase(agent).cancel_workflow("dev-001")

    assert result == {"success": True}
    agent.handle_request.assert_awaited_once_with(
        {"action": "cancel_workflow", "task_id": "dev-001"}
    )


@pytest.mark.asyncio
async def test_approve_workflow_forwards_human_context() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"success": True}

    result = await DevApiUseCase(agent).approve_workflow(
        DevWorkflowApprovalCommand(
            task_id="dev-high-1",
            operator="human:lead",
            approval_id="appr_dev_1",
        )
    )

    assert result == {"success": True}
    agent.handle_request.assert_awaited_once_with(
        {
            "action": "approve_workflow",
            "task_id": "dev-high-1",
            "approved_by": "human:lead",
            "approval_id": "appr_dev_1",
        }
    )


@pytest.mark.asyncio
async def test_approve_workflow_omits_empty_optional_fields() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {"success": True}

    await DevApiUseCase(agent).approve_workflow(
        DevWorkflowApprovalCommand(task_id="dev-high-1")
    )

    agent.handle_request.assert_awaited_once_with(
        {
            "action": "approve_workflow",
            "task_id": "dev-high-1",
        }
    )
