"""Application use cases for control-plane work items."""

from __future__ import annotations

from shared.schemas.event import EventTypes

from .domain.work_item import WorkItem as WorkItemAggregate
from .domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
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
) -> list[WorkItem]:
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
) -> WorkItem:
    """Return one work item in a company or raise not found."""
    work_item = await store.get_work_item(work_item_id)
    if work_item is None or work_item.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)
    return work_item


async def create_work_item_with_audit(
    store: ControlPlaneWorkItemStore,
    work_item: WorkItem,
    *,
    created_by: str,
) -> WorkItem:
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

    created = await store.create_work_item(work_item)
    await store.append_audit_event(
        AuditEvent(
            company_id=work_item.company_id,
            action=EventTypes.WORK_ITEM_CREATED,
            target_type="work_item",
            target_id=created.work_item_id,
            actor_type="user",
            actor_id=created_by,
            work_item_id=created.work_item_id,
            detail={
                "work_item_id": created.work_item_id,
                "status": created.status,
                "priority": created.priority,
                "goal_id": created.goal_id,
                "owner_agent_id": created.owner_agent_id,
                "owner_user_id": created.owner_user_id,
            },
        )
    )
    return created


async def update_work_item_status_with_audit(
    store: ControlPlaneWorkItemStore,
    *,
    company_id: str,
    work_item_id: str,
    status: WorkItemStatus | str,
    owner_agent_id: str | None,
    owner_user_id: str | None,
    actor_id: str,
    command: str | None = None,
    reason: str | None = None,
) -> WorkItem:
    """Update a work-item status and record its audit event."""
    existing = await store.get_work_item(work_item_id)
    if existing is None or existing.company_id != company_id:
        raise WorkItemNotFoundError(work_item_id)

    aggregate = WorkItemAggregate.from_record(existing)
    aggregate.transition_to(status)
    domain_events = aggregate.pull_events()
    status_value = aggregate.status.value
    updated = await store.update_work_item_status(
        work_item_id,
        status=status_value,
        owner_agent_id=owner_agent_id,
        owner_user_id=owner_user_id,
    )
    if updated is None:
        raise WorkItemNotFoundError(work_item_id)

    detail = {
        "status": updated.status,
        "owner_agent_id": updated.owner_agent_id,
        "owner_user_id": updated.owner_user_id,
    }
    if command:
        detail["command"] = command
    if reason:
        detail["reason"] = reason

    if domain_events:
        await append_control_plane_domain_event_audits(
            store,
            domain_events,
            DomainEventAuditContext(
                actor_type="user",
                actor_id=actor_id,
                work_item_id=updated.work_item_id,
                detail=detail,
            ),
        )
        return updated

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.WORK_ITEM_UPDATED,
            target_type="work_item",
            target_id=updated.work_item_id,
            actor_type="user",
            actor_id=actor_id,
            work_item_id=updated.work_item_id,
            detail=detail,
        )
    )
    return updated


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
