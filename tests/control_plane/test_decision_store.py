"""Tests for the dedicated control-plane decision store."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.decision_store import SqlAlchemyControlPlaneDecisionStore
from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    AuditEvent,
    CompanyContext,
    Decision,
    DecisionStatus,
    Goal,
    GoalStatus,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from shared.control_plane.tables import AuditEventTable
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore


@pytest.mark.asyncio
async def test_decision_store_owns_decision_queries(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    goal_store = SqlAlchemyControlPlaneGoalStore(db_session)
    work_item_store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    decision_store = SqlAlchemyControlPlaneDecisionStore(db_session)

    company = await company_store.create_company(
        CompanyContext(company_id="cmp_decision_store", name="Wisdoverse Cell")
    )
    goal = await goal_store.create_goal(
        Goal(
            company_id=company.company_id,
            title="Make decisions explicit",
            status=GoalStatus.ACTIVE,
        )
    )
    work_item = await work_item_store.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Extract decision persistence",
            status=WorkItemStatus.READY,
            priority=WorkItemPriority.HIGH,
        )
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_decision_store",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
        )
    )
    decision = await decision_store.create_decision(
        Decision(
            company_id=company.company_id,
            title="Keep repository as compatibility facade",
            rationale="The store should own Decision SQL before service extraction.",
            status=DecisionStatus.PROPOSED,
            run_id=run.run_id,
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            options=[{"id": "thin-facade", "label": "Thin facade"}],
            metadata={"source": "decision-store"},
        )
    )
    other_run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="qa-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_decision_store_other",
        )
    )
    other_decision = await decision_store.create_decision(
        Decision(
            company_id=company.company_id,
            title="Validate boundary",
            rationale="Audit-timeline queries need multiple run IDs.",
            status=DecisionStatus.REJECTED,
            run_id=other_run.run_id,
        )
    )

    rows = await decision_store.list_decisions(
        company_id=company.company_id,
        status=DecisionStatus.PROPOSED.value,
        run_id=run.run_id,
        goal_id=goal.goal_id,
        work_item_id=work_item.work_item_id,
    )
    run_rows = await decision_store.list_decisions(
        company_id=company.company_id,
        run_ids=[run.run_id, other_run.run_id],
    )
    fetched = await decision_store.get_decision(decision.decision_id)

    assert [row.decision_id for row in rows] == [decision.decision_id]
    assert {row.decision_id for row in run_rows} == {
        decision.decision_id,
        other_decision.decision_id,
    }
    assert fetched is not None
    assert fetched.options == [{"id": "thin-facade", "label": "Thin facade"}]
    assert fetched.metadata == {"source": "decision-store"}
    assert not hasattr(fetched, "metadata_json")


@pytest.mark.asyncio
async def test_decision_store_updates_status(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneDecisionStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_decision_status", name="Wisdoverse Cell")
    )
    decision = await store.create_decision(
        Decision(
            company_id=company.company_id,
            title="Adopt explicit state transitions",
            rationale="Decisions need visible status changes.",
        )
    )
    previous_updated_at = decision.updated_at

    updated = await store.update_decision_status(
        decision.decision_id,
        status=DecisionStatus.ACCEPTED.value,
        selected_option="thin-facade",
        decided_by="human:architect",
    )
    missing = await store.update_decision_status(
        "dec_missing",
        status=DecisionStatus.ACCEPTED.value,
    )

    assert updated is not None
    assert updated.status == DecisionStatus.ACCEPTED.value
    assert updated.selected_option == "thin-facade"
    assert updated.decided_by == "human:architect"
    assert updated.updated_at >= previous_updated_at
    assert missing is None


@pytest.mark.asyncio
async def test_decision_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneDecisionStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_decision_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="decision.created",
        target_type="decision",
        target_id="dec_001",
        idempotency_key="dec_001:created",
        detail={"source": "decision-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    result = await db_session.execute(
        select(AuditEventTable).where(
            AuditEventTable.company_id == company.company_id,
            AuditEventTable.idempotency_key == "dec_001:created",
        )
    )

    assert first.audit_event_id == second.audit_event_id
    assert len(list(result.scalars().all())) == 1
