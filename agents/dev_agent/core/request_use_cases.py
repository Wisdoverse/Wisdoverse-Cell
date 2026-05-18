"""Application use cases for Dev agent request dispatch."""
from __future__ import annotations

from typing import Any, Protocol

from shared.control_plane import ApprovalRequiredError
from shared.core import request_error
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..models.schemas import WorkflowPlan
from .domain.lifecycle.task_lifecycle import AWAITING_APPROVAL, FAILED
from .repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort

logger = get_logger("dev_agent.request_use_cases")


class DevApprovalGatePort(Protocol):
    async def approve_for_sensitive_action(
        self,
        approval_id: str | None,
        *,
        resolved_by: str,
    ) -> Any:
        ...


class DevWorkflowExecutorPort(Protocol):
    async def execute_workflow(
        self,
        plan: WorkflowPlan,
        task_record: Any,
        repo: DevTaskRepositoryPort,
    ) -> list[Event]:
        ...


class DevRequestUseCase:
    """Dispatch Dev request actions without leaking logic into the service shell."""

    def __init__(
        self,
        *,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        approval_gate: DevApprovalGatePort,
        workflow_executor: DevWorkflowExecutorPort,
    ) -> None:
        self._repo = repo
        self._log_repo = log_repo
        self._approval_gate = approval_gate
        self._workflow_executor = workflow_executor

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")

        if action == "get_task_status":
            return await self._get_task_status(request)
        if action == "list_active_workflows":
            return await self._list_active_workflows()
        if action == "list_failed":
            return await self._list_failed()
        if action == "retry_task":
            return await self._retry_task(request)
        if action == "cancel_workflow":
            return await self._cancel_workflow(request)
        if action == "approve_workflow":
            return await self._approve_workflow(request)

        return request_error(
            f"Unknown action: {action}",
            "unknown_action",
            action=action,
        )

    async def _get_task_status(self, request: dict[str, Any]) -> dict[str, Any]:
        wp_id = request.get("wp_id")
        if not wp_id:
            return request_error("wp_id required", "wp_id_required")

        task = await self._repo.get_by_wp_id(wp_id)
        if not task:
            return request_error(
                f"Task not found for wp_id={wp_id}",
                "dev_task_not_found",
                wp_id=wp_id,
            )

        return {
            "wp_id": task.wp_id,
            "status": task.status,
            "risk_level": task.risk_level,
            "workflow_id": task.workflow_id,
            "mr_url": task.mr_url,
            "retry_count": task.retry_count,
            "error_message": task.error_message,
            "created_at": str(task.created_at) if task.created_at else None,
        }

    async def _list_active_workflows(self) -> dict[str, Any]:
        tasks = await self._repo.list_active_tasks()
        return {
            "workflows": [
                {
                    "wp_id": task.wp_id,
                    "status": task.status,
                    "workflow_id": task.workflow_id,
                    "risk_level": task.risk_level,
                }
                for task in tasks
            ]
        }

    async def _list_failed(self) -> dict[str, Any]:
        tasks = await self._repo.list_failed_tasks()
        return {
            "workflows": [
                {
                    "wp_id": task.wp_id,
                    "status": task.status,
                    "error_message": task.error_message,
                    "failed_step": task.failed_step,
                    "retry_count": task.retry_count,
                }
                for task in tasks
            ]
        }

    async def _retry_task(self, request: dict[str, Any]) -> dict[str, Any]:
        task_id = request.get("task_id")
        if not task_id:
            return request_error("task_id required", "task_id_required")

        task = await self._repo.get_by_id(task_id)
        if not task or task.status != FAILED:
            return request_error(
                "Task not found or not in failed state",
                "dev_task_not_retryable",
                task_id=task_id,
            )

        success = await self._repo.update_status(
            task_id,
            "planning",
            retry_count=task.retry_count + 1,
        )
        return {"success": success, "task_id": task_id}

    async def _cancel_workflow(self, request: dict[str, Any]) -> dict[str, Any]:
        task_id = request.get("task_id")
        if not task_id:
            return request_error("task_id required", "task_id_required")

        success = await self._repo.update_status(
            task_id,
            "failed",
            error_message="Manually cancelled",
        )
        return {"success": success}

    async def _approve_workflow(self, request: dict[str, Any]) -> dict[str, Any]:
        task_id = request.get("task_id")
        if not task_id:
            return request_error("task_id required", "task_id_required")

        task = await self._repo.get_by_id(task_id)
        if not task or task.status != AWAITING_APPROVAL:
            return request_error(
                "Task not found or not awaiting approval",
                "dev_task_not_awaiting_approval",
                task_id=task_id,
            )

        workflow_log = await self._log_repo.get_by_task_id(task_id)
        if not workflow_log or not workflow_log.workflow_json:
            logger.error(
                "approve_missing_workflow_plan",
                task_id=task_id,
                msg="Cannot execute: workflow plan not found in logs",
            )
            return request_error(
                "Workflow plan not found - cannot execute without a plan",
                "workflow_plan_not_found",
                task_id=task_id,
            )

        approval_id = request.get("approval_id") or workflow_log.workflow_json.get(
            "control_plane_approval_id"
        )
        approved_by = request.get("approved_by") or request.get("operator")
        if approval_id and not approved_by:
            return request_error(
                "approved_by required for control-plane approval",
                "control_plane_approval_resolver_required",
                task_id=task_id,
                control_plane_approval_id=approval_id,
            )

        try:
            approval_decision = await self._approval_gate.approve_for_sensitive_action(
                approval_id,
                resolved_by=approved_by or "api",
            )
        except ApprovalRequiredError as exc:
            logger.warning(
                "approve_workflow_control_plane_required",
                task_id=task_id,
                approval_id=approval_id,
                error=str(exc),
            )
            return request_error(
                str(exc),
                "control_plane_approval_required",
                task_id=task_id,
            )

        plan = WorkflowPlan.model_validate(workflow_log.workflow_json)
        exec_events = await self._workflow_executor.execute_workflow(plan, task, self._repo)
        resolved_approval_id = (
            approval_decision.approval_id if approval_decision else approval_id
        )
        return {
            "success": True,
            "task_id": task_id,
            "workflow_started": bool(exec_events),
            "control_plane_approval_id": resolved_approval_id,
        }
