"""Application use cases for control-plane goals."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .goal_ports import ControlPlaneGoalStore
from .models import AuditEvent, CompanyContext, Goal, GoalStatus


class GoalNotFoundError(Exception):
    """Raised when a goal cannot be found in the target company."""


class ParentGoalNotFoundError(Exception):
    """Raised when a parent goal is missing or belongs to another company."""


async def list_goals(
    store: ControlPlaneGoalStore,
    *,
    company_id: str,
    status: str | None = None,
    owner_agent_id: str | None = None,
    owner_user_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List goals for one company."""
    return await store.list_goals(
        company_id=company_id,
        status=status,
        owner_agent_id=owner_agent_id,
        owner_user_id=owner_user_id,
        search=search,
        limit=limit,
    )


async def get_goal(
    store: ControlPlaneGoalStore,
    *,
    company_id: str,
    goal_id: str,
) -> Any:
    """Return one goal in a company or raise not found."""
    row = await store.get_goal(goal_id)
    if row is None or row.company_id != company_id:
        raise GoalNotFoundError(goal_id)
    return row


async def create_goal_with_audit(
    store: ControlPlaneGoalStore,
    goal: Goal,
    *,
    created_by: str,
) -> Any:
    """Create a goal, validate parent linkage, and record its audit event."""
    await _ensure_company(store, goal.company_id)
    if goal.parent_goal_id:
        parent = await store.get_goal(goal.parent_goal_id)
        if parent is None or parent.company_id != goal.company_id:
            raise ParentGoalNotFoundError(goal.parent_goal_id)

    row = await store.create_goal(goal)
    await store.append_audit_event(
        AuditEvent(
            company_id=goal.company_id,
            action=EventTypes.GOAL_CREATED,
            target_type="goal",
            target_id=row.goal_id,
            actor_type="user",
            actor_id=created_by,
            detail={
                "goal_id": row.goal_id,
                "status": row.status,
                "parent_goal_id": row.parent_goal_id,
                "owner_agent_id": row.owner_agent_id,
                "owner_user_id": row.owner_user_id,
            },
        )
    )
    return row


async def update_goal_status_with_audit(
    store: ControlPlaneGoalStore,
    *,
    company_id: str,
    goal_id: str,
    status: GoalStatus | str,
    current_value: float | None,
    actor_id: str,
) -> Any:
    """Update a goal status and record its audit event."""
    existing = await store.get_goal(goal_id)
    if existing is None or existing.company_id != company_id:
        raise GoalNotFoundError(goal_id)

    status_value = status.value if isinstance(status, GoalStatus) else status
    row = await store.update_goal_status(
        goal_id,
        status=status_value,
        current_value=current_value,
    )
    if row is None:
        raise GoalNotFoundError(goal_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.GOAL_UPDATED,
            target_type="goal",
            target_id=row.goal_id,
            actor_type="user",
            actor_id=actor_id,
            detail={
                "status": row.status,
                "current_value": row.current_value,
            },
        )
    )
    return row


async def _ensure_company(store: ControlPlaneGoalStore, company_id: str) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )
