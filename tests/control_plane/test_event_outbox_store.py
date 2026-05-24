"""Tests for the Control Plane event outbox store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.domain.company_context import CompanyContextCreated
from shared.control_plane.domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
from shared.control_plane.event_outbox_store import SqlAlchemyControlPlaneEventOutboxStore
from shared.control_plane.models import CompanyContext
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_domain_event_audit_is_staged_in_control_plane_outbox(
    db_session: AsyncSession,
) -> None:
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    audit_store = SqlAlchemyControlPlaneAuditEventStore(db_session)
    outbox_store = SqlAlchemyControlPlaneEventOutboxStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))

    appended = await append_control_plane_domain_event_audits(
        audit_store,
        [
            CompanyContextCreated(
                company_id=company.company_id,
                name_length=len(company.name),
                mission_length=len(company.mission),
                metadata_keys=("source",),
            )
        ],
        DomainEventAuditContext(
            actor_type="system",
            actor_id="control-plane",
            trace_id="trace_control_plane_outbox",
        ),
    )

    pending = await outbox_store.list_pending(limit=10)

    assert len(appended) == 1
    assert len(pending) == 1
    row = pending[0]
    assert row.event_type == EventTypes.COMPANY_CREATED
    assert row.source_agent == "control-plane"
    assert row.status == "pending"
    assert row.trace_id == "trace_control_plane_outbox"
    assert row.correlation_id == appended[0].audit_event_id
    assert row.payload["audit_event_id"] == appended[0].audit_event_id
    assert row.payload["domain_event"] == "CompanyContextCreated"
    assert row.payload["company_id"] == company.company_id
    assert row.payload["detail"]["metadata_keys"] == ["source"]
