"""Application use cases for control-plane work items."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .models import (
    AuditEvent,
    CompanyContext,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from .work_item_ports import ControlPlaneWorkItemStore


class WorkItemGoalNotFoundError(Exception):
    """Raised when the linked goal is missing or belongs to another company."""


class WorkItemDependencyNotFoundError(Exception):
    """Raised when a dependency is missing or belongs to another company."""


class WorkItemNotFoundError(Exception):
    """Raised when a work item cannot be found in the target company."""


async def list_work_items(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    status: str | None = None,
    priority: str | None = None,
    goal_id: str | None = None,
    owner_agent_id: str | None = None,
    owner_user_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List work items for one company."""
    return await store.list_work_items(
        company_id=company_id,
        status=status,
        priority=priority,
        goal_id=goal_id,
        owner_agent_id=owner_agent_id,
        owner_user_id=owner_user_id,
        search=search,
        limit=limit,
    )


async def get_work_item(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
) -> Any:
    """Return one work item in a company or raise not found."""
    row = await store.get_work_item(work_item_id)
    if row is None or row.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)
    return row


async def create_work_item_with_audit(
    store: ControlPlaneWorkItemStore,
    work_item: WorkItem,
    *,
    created_by: str,
) -> Any:
    """Create a work item, validate links, and record its audit event."""
    await _ensure_company(store, work_item.company_id)
    if work_item.goal_id:
        goal = await store.get_goal(work_item.goal_id)
        if goal is None or goal.company_id != work_item.company_id:
            raise WorkItemGoalNotFoundError(work_item.goal_id)

    for dependency_id in work_item.dependencies:
        dependency = await store.get_work_item(dependency_id)
        if dependency is None or dependency.company_id != work_item.company_id:
            raise WorkItemDependencyNotFoundError(dependency_id)

    row = await store.create_work_item(work_item)
    await store.append_audit_event(
        AuditEvent(
            company_id=work_item.company_id,
            action=EventTypes.WORK_ITEM_CREATED,
            target_type="work_item",
            target_id=row.work_item_id,
            actor_type="user",
            actor_id=created_by,
            work_item_id=row.work_item_id,
            detail={
                "work_item_id": row.work_item_id,
                "status": row.status,
                "priority": row.priority,
                "goal_id": row.goal_id,
                "owner_agent_id": row.owner_agent_id,
                "owner_user_id": row.owner_user_id,
            },
        )
    )
    return row


async def update_work_item_status_with_audit(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
    status: WorkItemStatus | str,
    owner_agent_id: str | None,
    owner_user_id: str | None,
    actor_id: str,
) -> Any:
    """Update a work-item status and record its audit event."""
    existing = await store.get_work_item(work_item_id)
    if existing is None or existing.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)

    status_value = status.value if isinstance(status, WorkItemStatus) else status
    row = await store.update_work_item_status(
        work_item_id,
        status=status_value,
        owner_agent_id=owner_agent_id,
        owner_user_id=owner_user_id,
    )
    if row is None:
        raise WorkItemNotFoundError(work_item_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.WORK_ITEM_UPDATED,
            target_type="work_item",
            target_id=row.work_item_id,
            actor_type="user",
            actor_id=actor_id,
            work_item_id=row.work_item_id,
            detail={
                "status": row.status,
                "owner_agent_id": row.owner_agent_id,
                "owner_user_id": row.owner_user_id,
            },
        )
    )
    return row


def enum_value(value: WorkItemPriority | WorkItemStatus | str | None) -> str | None:
    """Return a persistence-ready enum value."""
    if value is None:
        return None
    if isinstance(value, WorkItemPriority | WorkItemStatus):
        return value.value
    return value


async def _ensure_company(
    store: ControlPlaneWorkItemStore,
    company_id: str,
) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )
