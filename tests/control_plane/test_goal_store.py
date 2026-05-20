"""Tests for the dedicated control-plane goal store."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.models import AuditEvent, CompanyContext, Goal, GoalStatus
from shared.control_plane.tables import AuditEventTable


@pytest.mark.asyncio
async def test_goal_store_owns_goal_queries(db_session: AsyncSession) -> None:
    store = SqlAlchemyControlPlaneGoalStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_goal_store", name="Wisdoverse Cell")
    )
    parent = await store.create_goal(
        Goal(
            company_id=company.company_id,
            title="Make SPEC executable",
            status=GoalStatus.ACTIVE,
            owner_agent_id="requirement-manager",
            success_metric="accepted requirements",
        )
    )
    child = await store.create_goal(
        Goal(
            company_id=company.company_id,
            parent_goal_id=parent.goal_id,
            title="Ship control-plane store boundaries",
            status=GoalStatus.DRAFT,
            owner_user_id="human:architect",
            success_metric="repository facade reduced",
        )
    )

    active_goals = await store.list_goals(
        company_id=company.company_id,
        status=GoalStatus.ACTIVE.value,
        owner_agent_id="requirement-manager",
        search="SPEC",
    )
    draft_goals = await store.list_goals(
        company_id=company.company_id,
        status=GoalStatus.DRAFT.value,
        owner_user_id="human:architect",
        search="store",
    )
    updated = await store.update_goal_status(
        child.goal_id,
        status=GoalStatus.ACTIVE.value,
        current_value=0.5,
    )

    assert [goal.goal_id for goal in active_goals] == [parent.goal_id]
    assert [goal.goal_id for goal in draft_goals] == [child.goal_id]
    assert updated is not None
    assert updated.status == GoalStatus.ACTIVE.value
    assert updated.current_value == 0.5


@pytest.mark.asyncio
async def test_goal_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneGoalStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_goal_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="goal.created",
        target_type="goal",
        target_id="goal_001",
        idempotency_key="goal_001:created",
        detail={"source": "goal-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    result = await db_session.execute(
        select(AuditEventTable).where(
            AuditEventTable.company_id == company.company_id,
            AuditEventTable.idempotency_key == "goal_001:created",
        )
    )

    assert first.audit_event_id == second.audit_event_id
    assert len(list(result.scalars().all())) == 1
