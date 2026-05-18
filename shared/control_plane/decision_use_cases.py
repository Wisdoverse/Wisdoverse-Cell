"""Application use cases for control-plane decisions."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .decision_ports import ControlPlaneDecisionStore
from .models import AuditEvent, CompanyContext, Decision, DecisionStatus


class DecisionGoalNotFoundError(Exception):
    """Raised when the linked goal is missing or belongs to another company."""


class DecisionLinkMismatchError(Exception):
    """Raised when linked run, work item, and goal references disagree."""


class DecisionNotFoundError(Exception):
    """Raised when a decision cannot be found in the target company."""


class DecisionRunNotFoundError(Exception):
    """Raised when the linked run is missing or belongs to another company."""


class DecisionWorkItemNotFoundError(Exception):
    """Raised when the linked work item is missing or belongs to another company."""


async def list_decisions(
    store: ControlPlaneDecisionStore,
    *,
    company_id: str,
    status: str | None = None,
    run_id: str | None = None,
    goal_id: str | None = None,
    work_item_id: str | None = None,
    limit: int = 50,
) -> list[Any]:
    """List decisions for one company."""
    return await store.list_decisions(
        company_id=company_id,
        status=status,
        run_id=run_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        limit=limit,
    )


async def get_decision(
    store: ControlPlaneDecisionStore,
    *,
    company_id: str,
    decision_id: str,
) -> Any:
    """Return one decision in a company or raise not found."""
    row = await store.get_decision(decision_id)
    if row is None or row.company_id != company_id:
        raise DecisionNotFoundError(decision_id)
    return row


async def create_decision_with_audit(
    store: ControlPlaneDecisionStore,
    decision: Decision,
    *,
    created_by: str,
) -> Any:
    """Create a decision, validate execution links, and record its audit event."""
    await _ensure_company(store, decision.company_id)
    goal_id, work_item_id = await _validate_execution_links(
        store,
        company_id=decision.company_id,
        run_id=decision.run_id,
        work_item_id=decision.work_item_id,
        goal_id=decision.goal_id,
    )

    row = await store.create_decision(
        decision.model_copy(
            update={
                "goal_id": goal_id,
                "work_item_id": work_item_id,
            }
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=decision.company_id,
            action=EventTypes.DECISION_CREATED,
            target_type="decision",
            target_id=row.decision_id,
            actor_type="user",
            actor_id=created_by,
            run_id=row.run_id,
            work_item_id=row.work_item_id,
            detail={
                "decision_id": row.decision_id,
                "status": row.status,
                "goal_id": row.goal_id,
                "work_item_id": row.work_item_id,
                "run_id": row.run_id,
            },
        )
    )
    return row


async def update_decision_status_with_audit(
    store: ControlPlaneDecisionStore,
    *,
    company_id: str,
    decision_id: str,
    status: DecisionStatus | str,
    selected_option: str | None,
    decided_by: str | None,
    actor_id: str,
) -> Any:
    """Update a decision status and record its audit event."""
    existing = await store.get_decision(decision_id)
    if existing is None or existing.company_id != company_id:
        raise DecisionNotFoundError(decision_id)

    status_value = status.value if isinstance(status, DecisionStatus) else status
    row = await store.update_decision_status(
        decision_id,
        status=status_value,
        selected_option=selected_option,
        decided_by=decided_by,
    )
    if row is None:
        raise DecisionNotFoundError(decision_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.DECISION_UPDATED,
            target_type="decision",
            target_id=row.decision_id,
            actor_type="user",
            actor_id=actor_id,
            run_id=row.run_id,
            work_item_id=row.work_item_id,
            detail={
                "status": row.status,
                "selected_option": row.selected_option,
                "decided_by": row.decided_by,
                "goal_id": row.goal_id,
            },
        )
    )
    return row


async def _ensure_company(
    store: ControlPlaneDecisionStore,
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


async def _validate_execution_links(
    store: ControlPlaneDecisionStore,
    *,
    company_id: str,
    run_id: str | None = None,
    work_item_id: str | None = None,
    goal_id: str | None = None,
) -> tuple[str | None, str | None]:
    resolved_goal_id = goal_id
    resolved_work_item_id = work_item_id
    if run_id:
        run = await store.get_agent_run(run_id)
        if run is None or run.company_id != company_id:
            raise DecisionRunNotFoundError(run_id)
        if run.work_item_id:
            if resolved_work_item_id and resolved_work_item_id != run.work_item_id:
                raise DecisionLinkMismatchError("work_item")
            resolved_work_item_id = run.work_item_id
        if run.goal_id:
            if resolved_goal_id and resolved_goal_id != run.goal_id:
                raise DecisionLinkMismatchError("goal")
            resolved_goal_id = run.goal_id
    if resolved_work_item_id:
        work_item = await store.get_work_item(resolved_work_item_id)
        if work_item is None or work_item.company_id != company_id:
            raise DecisionWorkItemNotFoundError(resolved_work_item_id)
        if work_item.goal_id:
            if resolved_goal_id and resolved_goal_id != work_item.goal_id:
                raise DecisionLinkMismatchError("goal")
            resolved_goal_id = work_item.goal_id
    if resolved_goal_id:
        goal = await store.get_goal(resolved_goal_id)
        if goal is None or goal.company_id != company_id:
            raise DecisionGoalNotFoundError(resolved_goal_id)
    return resolved_goal_id, resolved_work_item_id
