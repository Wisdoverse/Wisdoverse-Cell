"""Application use cases for Dev Agent HTTP operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DevApiAgentPort(Protocol):
    """Agent operations required by the Dev HTTP application use cases."""

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an agent request action."""


@dataclass(frozen=True, slots=True)
class DevWorkflowApprovalCommand:
    """Command for approving a paused Dev workflow."""

    task_id: str
    operator: str = ""
    approval_id: str | None = None


class DevApiUseCase:
    """Application boundary used by Dev HTTP routes."""

    def __init__(self, agent: DevApiAgentPort):
        self._agent = agent

    async def list_tasks(self) -> dict[str, Any]:
        return await self._agent.handle_request({"action": "list_active_workflows"})

    async def list_failed_tasks(self) -> dict[str, Any]:
        return await self._agent.handle_request({"action": "list_failed"})

    async def get_task_status(self, wp_id: int) -> dict[str, Any]:
        return await self._agent.handle_request(
            {"action": "get_task_status", "wp_id": wp_id}
        )

    async def retry_task(self, task_id: str) -> dict[str, Any]:
        return await self._agent.handle_request(
            {"action": "retry_task", "task_id": task_id}
        )

    async def cancel_workflow(self, task_id: str) -> dict[str, Any]:
        return await self._agent.handle_request(
            {"action": "cancel_workflow", "task_id": task_id}
        )

    async def approve_workflow(
        self,
        command: DevWorkflowApprovalCommand,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "action": "approve_workflow",
            "task_id": command.task_id,
        }
        if command.operator:
            request["approved_by"] = command.operator
        if command.approval_id:
            request["approval_id"] = command.approval_id
        return await self._agent.handle_request(request)
