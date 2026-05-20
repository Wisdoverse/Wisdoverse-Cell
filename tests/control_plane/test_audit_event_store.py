"""Tests for the control-plane audit event store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.models import AuditEvent, CompanyContext


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
