"""Tests for control-plane work-item use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.domain.work_item import InvalidWorkItemTransitionError
from shared.control_plane.models import WorkItem, WorkItemStatus
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore
from shared.control_plane.work_item_use_cases import (
    create_work_item_with_audit,
    update_work_item_status_with_audit,
)
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_work_item_status_use_case_routes_through_aggregate(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    work_item = await create_work_item_with_audit(
        store,
        WorkItem(
            company_id="cmp_work_item_use_case",
            title="Execute delivery task",
            status=WorkItemStatus.QUEUED,
        ),
        created_by="human:pm",
    )

    updated = await update_work_item_status_with_audit(
        store,
        company_id="cmp_work_item_use_case",
        work_item_id=work_item.work_item_id,
        status=WorkItemStatus.RUNNING,
        owner_agent_id="dev-agent",
        owner_user_id=None,
        actor_id="human:pm",
    )

    assert updated.status == WorkItemStatus.RUNNING.value
    assert updated.owner_agent_id == "dev-agent"
    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id="cmp_work_item_use_case",
        target_type="work_item",
        target_id=work_item.work_item_id,
    )
    updated_audit = next(event for event in audits if event.action == EventTypes.WORK_ITEM_UPDATED)
    assert updated_audit.detail["domain_event"] == "WorkItemStatusChanged"
    assert updated_audit.detail["from_status"] == WorkItemStatus.QUEUED.value
    assert updated_audit.detail["to_status"] == WorkItemStatus.RUNNING.value
    assert updated_audit.detail["owner_agent_id"] == "dev-agent"


@pytest.mark.asyncio
async def test_work_item_status_use_case_blocks_illegal_domain_transition(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    work_item = await create_work_item_with_audit(
        store,
        WorkItem(
            company_id="cmp_work_item_use_case_invalid",
            title="Cancelled delivery task",
            status=WorkItemStatus.CANCELLED,
        ),
        created_by="human:pm",
    )

    with pytest.raises(InvalidWorkItemTransitionError):
        await update_work_item_status_with_audit(
            store,
            company_id="cmp_work_item_use_case_invalid",
            work_item_id=work_item.work_item_id,
            status=WorkItemStatus.RUNNING,
            owner_agent_id="dev-agent",
            owner_user_id=None,
            actor_id="human:pm",
        )
