"""Tests for control-plane goal use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.domain.goal import InvalidGoalTransitionError
from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.goal_use_cases import (
    create_goal_with_audit,
    update_goal_status_with_audit,
)
from shared.control_plane.models import Goal, GoalStatus
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_goal_status_use_case_routes_through_aggregate(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneGoalStore(db_session)
    goal = await create_goal_with_audit(
        store,
        Goal(
            company_id="cmp_goal_use_case",
            title="Ship operator objective",
            status=GoalStatus.DRAFT,
            target_value=100,
        ),
        created_by="human:pm",
    )

    updated = await update_goal_status_with_audit(
        store,
        company_id="cmp_goal_use_case",
        goal_id=goal.goal_id,
        status=GoalStatus.COMPLETED,
        current_value=None,
        actor_id="human:pm",
    )

    assert updated.status == GoalStatus.COMPLETED.value
    assert updated.current_value == 100
    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id="cmp_goal_use_case",
        target_type="goal",
        target_id=goal.goal_id,
    )
    updated_audit = next(event for event in audits if event.action == EventTypes.GOAL_UPDATED)
    assert updated_audit.detail["domain_event"] == "GoalStatusChanged"
    assert updated_audit.detail["from_status"] == GoalStatus.DRAFT.value
    assert updated_audit.detail["to_status"] == GoalStatus.COMPLETED.value
    assert updated_audit.detail["current_value"] == 100


@pytest.mark.asyncio
async def test_goal_status_use_case_blocks_illegal_domain_transition(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneGoalStore(db_session)
    goal = await create_goal_with_audit(
        store,
        Goal(
            company_id="cmp_goal_use_case_invalid",
            title="Cancelled operator objective",
            status=GoalStatus.CANCELLED,
        ),
        created_by="human:pm",
    )

    with pytest.raises(InvalidGoalTransitionError):
        await update_goal_status_with_audit(
            store,
            company_id="cmp_goal_use_case_invalid",
            goal_id=goal.goal_id,
            status=GoalStatus.ACTIVE,
            current_value=None,
            actor_id="human:pm",
        )
