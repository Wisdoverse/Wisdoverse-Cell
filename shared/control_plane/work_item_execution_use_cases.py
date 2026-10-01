"""Application use cases for executing control-plane work items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_operation_ports import ControlPlaneAgentOperationStore
from .agent_operation_use_cases import (
    AgentDefinitionNotFoundError,
    AgentWakeupUseCaseResult,
    wake_agent_definition,
)
from .agent_runner import AgentWakeupError
from .domain.work_item import work_item_status_from_agent_run_status
from .models import WorkItem, WorkItemStatus
from .work_item_ports import ControlPlaneWorkItemStore
from .work_item_use_cases import WorkItemNotFoundError, update_work_item_status_with_audit


class WorkItemExecutionAgentRequiredError(Exception):
    """Raised when a work item has no assigned agent and none is supplied."""


@dataclass(frozen=True, slots=True)
class WorkItemExecutionResult:
    """Result of executing a work item through an owning agent."""

    work_item: WorkItem
    agent_wakeup: AgentWakeupUseCaseResult


async def run_work_item_with_agent(
    work_items: ControlPlaneWorkItemStore,
    agent_operations: ControlPlaneAgentOperationStore,
    *,
    company_id: str,
    work_item_id: str,
    agent_id: str | None = None,
    input_payload: dict[str, Any] | None = None,
    actor_id: str = "api",
    trace_id: str | None = None,
    idempotency_key: str | None = None,
) -> WorkItemExecutionResult:
    """Run a work item through its owner agent or an explicitly supplied agent."""
    work_item = await work_items.get_work_item(work_item_id)
    if work_item is None or work_item.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)

    resolved_agent_id = (agent_id or work_item.owner_agent_id or "").strip()
    if not resolved_agent_id:
        raise WorkItemExecutionAgentRequiredError(work_item_id)

    try:
        wakeup = await wake_agent_definition(
            agent_operations,
            company_id=company_id,
            agent_id=resolved_agent_id,
            input_payload=_build_agent_input_payload(work_item, input_payload),
            actor_id=actor_id,
            trace_id=trace_id,
            goal_id=work_item.goal_id,
            work_item_id=work_item.work_item_id,
            idempotency_key=idempotency_key,
        )
    except AgentDefinitionNotFoundError:
        raise
    except AgentWakeupError as exc:
        if exc.error_category in {"execution_denied", "uncertain_effects"}:
            raise
        await update_work_item_status_with_audit(
            work_items,
            company_id=company_id,
            work_item_id=work_item_id,
            status=WorkItemStatus.CANCELLED if exc.error_category == "cancelled" else WorkItemStatus.FAILED,
            owner_agent_id=resolved_agent_id,
            owner_user_id=None,
            actor_id=actor_id,
        )
        raise

    final_status = _work_item_status_from_run(wakeup)
    updated = await update_work_item_status_with_audit(
        work_items,
        company_id=company_id,
        work_item_id=work_item_id,
        status=final_status,
        owner_agent_id=resolved_agent_id,
        owner_user_id=None,
        actor_id=actor_id,
    )
    return WorkItemExecutionResult(work_item=updated, agent_wakeup=wakeup)


def _build_agent_input_payload(
    work_item: WorkItem,
    input_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(input_payload or {})
    payload["work_item"] = {
            "work_item_id": work_item.work_item_id,
            "company_id": work_item.company_id,
            "title": work_item.title,
            "description": work_item.description,
            "priority": work_item.priority,
            "goal_id": work_item.goal_id,
            "owner_agent_id": work_item.owner_agent_id,
            "owner_user_id": work_item.owner_user_id,
            "source": work_item.source,
            "external_ref": work_item.external_ref,
            "dependencies": list(work_item.dependencies or []),
            "approval_required": work_item.approval_required,
            "metadata": dict(work_item.metadata or {}),
        }
    return payload


def _work_item_status_from_run(
    result: AgentWakeupUseCaseResult,
) -> WorkItemStatus:
    if result.run is None:
        return work_item_status_from_agent_run_status(None)
    if result.run.status == "succeeded":
        return WorkItemStatus.BLOCKED  # Output awaits explicit evidence acceptance.
    return work_item_status_from_agent_run_status(result.run.status)


__all__ = [
    "WorkItemExecutionAgentRequiredError",
    "WorkItemExecutionResult",
    "run_work_item_with_agent",
]
