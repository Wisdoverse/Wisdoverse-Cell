"""Tests for the dedicated control-plane work-item store."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.models import (
    AuditEvent,
    CompanyContext,
    Goal,
    GoalStatus,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from shared.control_plane.tables import AuditEventTable
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore


@pytest.mark.asyncio
async def test_work_item_store_owns_work_item_queries(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    goal_store = SqlAlchemyControlPlaneGoalStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_work_item_store", name="Wisdoverse Cell")
    )
    goal = await goal_store.create_goal(
        Goal(
            company_id=company.company_id,
            title="Make SPEC executable",
            status=GoalStatus.ACTIVE,
        )
    )
    dependency = await store.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Define control-plane goal boundary",
            status=WorkItemStatus.COMPLETED,
            priority=WorkItemPriority.HIGH,
            owner_agent_id="pjm-agent",
            external_ref="spec-work-001",
        )
    )
    work_item = await store.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Extract work-item persistence",
            description="Move WorkItem SQL out of the repository facade",
            status=WorkItemStatus.READY,
            priority=WorkItemPriority.HIGH,
            owner_user_id="human:architect",
            external_ref="spec-work-002",
            dependencies=[dependency.work_item_id],
        )
    )

    rows = await store.list_work_items(
        company_id=company.company_id,
        status=WorkItemStatus.READY.value,
        priority=WorkItemPriority.HIGH.value,
        goal_id=goal.goal_id,
        owner_user_id="human:architect",
        search="persistence",
    )
    updated = await store.update_work_item_status(
        work_item.work_item_id,
        status=WorkItemStatus.RUNNING.value,
        owner_agent_id="dev-agent",
    )

    assert rows == [work_item]
    assert work_item.dependencies == [dependency.work_item_id]
    assert updated is not None
    assert updated.status == WorkItemStatus.RUNNING.value
    assert updated.owner_agent_id == "dev-agent"
    assert updated.owner_user_id == "human:architect"


@pytest.mark.asyncio
async def test_work_item_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_work_item_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="work_item.created",
        target_type="work_item",
        target_id="work_001",
        work_item_id="work_001",
        idempotency_key="work_001:created",
        detail={"source": "work-item-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    result = await db_session.execute(
        select(AuditEventTable).where(
            AuditEventTable.company_id == company.company_id,
            AuditEventTable.idempotency_key == "work_001:created",
        )
    )

    assert first.audit_event_id == second.audit_event_id
    assert len(list(result.scalars().all())) == 1
