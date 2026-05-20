"""Tests for the dedicated control-plane company store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.models import AuditEvent, CompanyContext
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_company_store_owns_company_queries(db_session: AsyncSession) -> None:
    store = SqlAlchemyControlPlaneCompanyStore(db_session)

    company = await store.create_company(
        CompanyContext(
            company_id="cmp_company_store",
            name="Wisdoverse Cell",
            mission="Operate with agents",
            metadata={"stage": "store"},
        )
    )
    rows = await store.list_companies(search="wisdoverse")
    updated = await store.update_company_context(
        company.company_id,
        name="Wisdoverse Cell Public",
        metadata={"stage": "store", "status": "public"},
    )

    assert rows[0].company_id == "cmp_company_store"
    assert updated is not None
    assert updated.name == "Wisdoverse Cell Public"
    assert updated.metadata_json == {"stage": "store", "status": "public"}


@pytest.mark.asyncio
async def test_company_store_records_audit_events(db_session: AsyncSession) -> None:
    store = SqlAlchemyControlPlaneCompanyStore(db_session)
    repo = ControlPlaneRepository(db_session)

    await store.create_company(
        CompanyContext(company_id="cmp_company_store", name="Wisdoverse Cell")
    )
    event = await store.append_audit_event(
        AuditEvent(
            company_id="cmp_company_store",
            action=EventTypes.COMPANY_UPDATED,
            target_type="company",
            target_id="cmp_company_store",
            actor_type="user",
            actor_id="test",
            detail={"source": "company-store"},
        )
    )
    rows = await repo.list_audit_events(company_id="cmp_company_store")

    assert event.company_id == "cmp_company_store"
    assert rows[0].detail["source"] == "company-store"
