"""Tests for the control-plane audit event store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.models import AgentRunStatus, AuditEvent, CompanyContext


@pytest.mark.asyncio
async def test_audit_events_are_idempotent_and_queryable(
    db_session: AsyncSession,
):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneAuditEventStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    event = AuditEvent(
        company_id=company.company_id,
        action="agent_role.created",
        target_type="agent_role",
        target_id="cto",
        trace_id="trace_audit_store",
        run_id="run_audit_store",
        idempotency_key="audit-store:cto",
        detail={"source": "test"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    rows = await store.list_audit_events(
        company_id=company.company_id,
        trace_id="trace_audit_store",
        run_id="run_audit_store",
        target_type="agent_role",
        target_id="cto",
    )

    assert first.audit_event_id == second.audit_event_id
    assert [row.audit_event_id for row in rows] == [first.audit_event_id]


@pytest.mark.asyncio
async def test_audit_event_store_normalizes_through_domain_aggregate(
    db_session: AsyncSession,
):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneAuditEventStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))

    created = await store.append_audit_event(
        AuditEvent(
            company_id=f" {company.company_id} ",
            action=" budget_usage.recorded ",
            target_type=" budget_usage ",
            target_id=" usage_test ",
            actor_type=" ",
            actor_id=" system:budget ",
            idempotency_key=" ",
            detail={
                "status": AgentRunStatus.SUCCEEDED,
                "metadata_keys": ("model", "cost"),
                "nested": {"from_status": AgentRunStatus.RUNNING},
            },
        )
    )

    assert created.company_id == company.company_id
    assert created.action == "budget_usage.recorded"
    assert created.target_type == "budget_usage"
    assert created.target_id == "usage_test"
    assert created.actor_type == "system"
    assert created.actor_id == "system:budget"
    assert created.idempotency_key is None
    assert created.detail == {
        "status": "succeeded",
        "metadata_keys": ["model", "cost"],
        "nested": {"from_status": "running"},
    }
