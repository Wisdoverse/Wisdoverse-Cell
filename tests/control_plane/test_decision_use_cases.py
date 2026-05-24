"""Tests for control-plane decision use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.decision_store import SqlAlchemyControlPlaneDecisionStore
from shared.control_plane.decision_use_cases import (
    create_decision_with_audit,
    update_decision_status_with_audit,
)
from shared.control_plane.domain.decision import InvalidDecisionTransitionError
from shared.control_plane.models import Decision, DecisionStatus


@pytest.mark.asyncio
async def test_decision_status_use_case_routes_through_aggregate(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneDecisionStore(db_session)
    decision = await create_decision_with_audit(
        store,
        Decision(
            company_id="cmp_decision_use_case",
            title="Choose release",
            rationale="Release decision needs an explicit audit record.",
        ),
        created_by="human:lead",
    )

    updated = await update_decision_status_with_audit(
        store,
        company_id="cmp_decision_use_case",
        decision_id=decision.decision_id,
        status=DecisionStatus.ACCEPTED,
        selected_option="ship",
        decided_by="human:lead",
        actor_id="human:lead",
    )

    assert updated.status == DecisionStatus.ACCEPTED.value
    assert updated.selected_option == "ship"
    assert updated.decided_by == "human:lead"


@pytest.mark.asyncio
async def test_decision_status_use_case_blocks_illegal_domain_transition(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneDecisionStore(db_session)
    decision = await create_decision_with_audit(
        store,
        Decision(
            company_id="cmp_decision_use_case_invalid",
            title="Accepted release",
            rationale="Accepted decisions may only be superseded.",
            status=DecisionStatus.ACCEPTED,
        ),
        created_by="human:lead",
    )

    with pytest.raises(InvalidDecisionTransitionError):
        await update_decision_status_with_audit(
            store,
            company_id="cmp_decision_use_case_invalid",
            decision_id=decision.decision_id,
            status=DecisionStatus.REJECTED,
            selected_option=None,
            decided_by="human:lead",
            actor_id="human:lead",
        )
