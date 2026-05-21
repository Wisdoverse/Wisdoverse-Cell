"""Application use cases for control-plane work-item operations."""
from __future__ import annotations

from .models import WorkItem, WorkItemStatus
from .work_item_ports import ControlPlaneWorkItemStore
from .work_item_use_cases import WorkItemNotFoundError, update_work_item_status_with_audit


class WorkItemAssigneeRequiredError(Exception):
    """Raised when a reassign command does not include an owner."""


class WorkItemCloseStatusError(Exception):
    """Raised when a close command requests a non-terminal status."""


async def reassign_work_item(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
    owner_agent_id: str | None,
    owner_user_id: str | None,
    actor_id: str,
    reason: str | None = None,
) -> WorkItem:
    """Change work-item ownership without changing its lifecycle status."""
    existing = await _get_company_work_item(store, company_id, work_item_id)
    if not owner_agent_id and not owner_user_id:
        raise WorkItemAssigneeRequiredError(work_item_id)
    return await update_work_item_status_with_audit(
        store,
        company_id=company_id,
        work_item_id=work_item_id,
        status=existing.status,
        owner_agent_id=owner_agent_id,
        owner_user_id=owner_user_id,
        actor_id=actor_id,
        command="reassign",
        reason=reason,
    )


async def block_work_item(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
    actor_id: str,
    reason: str,
) -> WorkItem:
    """Mark a work item blocked and record the blocking reason."""
    existing = await _get_company_work_item(store, company_id, work_item_id)
    return await update_work_item_status_with_audit(
        store,
        company_id=company_id,
        work_item_id=work_item_id,
        status=WorkItemStatus.BLOCKED,
        owner_agent_id=existing.owner_agent_id,
        owner_user_id=existing.owner_user_id,
        actor_id=actor_id,
        command="block",
        reason=reason,
    )


async def close_work_item(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
    status: WorkItemStatus,
    actor_id: str,
    reason: str | None = None,
) -> WorkItem:
    """Close a work item with a terminal status."""
    if status not in {
        WorkItemStatus.COMPLETED,
        WorkItemStatus.CANCELLED,
        WorkItemStatus.FAILED,
    }:
        raise WorkItemCloseStatusError(status)
    existing = await _get_company_work_item(store, company_id, work_item_id)
    return await update_work_item_status_with_audit(
        store,
        company_id=company_id,
        work_item_id=work_item_id,
        status=status,
        owner_agent_id=existing.owner_agent_id,
        owner_user_id=existing.owner_user_id,
        actor_id=actor_id,
        command="close",
        reason=reason,
    )


async def _get_company_work_item(
    store: ControlPlaneWorkItemStore,
    company_id: str,
    work_item_id: str,
) -> WorkItem:
    work_item = await store.get_work_item(work_item_id)
    if work_item is None or work_item.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)
    return work_item


__all__ = [
    "WorkItemAssigneeRequiredError",
    "WorkItemCloseStatusError",
    "block_work_item",
    "close_work_item",
    "reassign_work_item",
]
