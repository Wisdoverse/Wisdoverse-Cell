"""Tests for control-plane company application use cases."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.company_use_cases import (
    create_company_with_audit,
    update_company_with_audit,
)
from shared.control_plane.domain.company_context import InvalidCompanyContextError
from shared.control_plane.store_factory import ControlPlaneStores
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_company_create_uses_aggregate_policy_and_audit(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)

    company = await create_company_with_audit(
        stores.companies,
        company_id="cmp_company_domain",
        name="  Wisdoverse Cell  ",
        mission="  Operate with agents  ",
        metadata={"stage": "domain"},
        created_by="human:operator",
    )
    audits = await stores.audit_events.list_audit_events(
        company_id=company.company_id,
        target_type="company",
    )

    assert company.name == "Wisdoverse Cell"
    assert company.mission == "Operate with agents"
    assert company.metadata == {"stage": "domain"}
    assert len(audits) == 1
    assert audits[0].action == EventTypes.COMPANY_CREATED
    assert audits[0].actor_id == "human:operator"
    assert audits[0].detail["domain_event"] == "CompanyContextCreated"
    assert audits[0].detail["metadata_keys"] == ["stage"]
    assert "Wisdoverse Cell" not in str(audits[0].detail)


@pytest.mark.asyncio
async def test_company_update_uses_aggregate_policy_and_audit(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await create_company_with_audit(
        stores.companies,
        company_id="cmp_company_update_domain",
        name="Wisdoverse Cell",
        mission="Operate with agents",
        metadata={},
        created_by="human:operator",
    )

    updated = await update_company_with_audit(
        stores.companies,
        company_id=company.company_id,
        name="  Wisdoverse Cell Public  ",
        mission=None,
        metadata={"stage": "public"},
        actor_id="human:operator",
    )
    audits = await stores.audit_events.list_audit_events(
        company_id=company.company_id,
        target_type="company",
    )

    assert updated.name == "Wisdoverse Cell Public"
    assert updated.mission == "Operate with agents"
    assert updated.metadata == {"stage": "public"}
    assert audits[0].action == EventTypes.COMPANY_UPDATED
    assert audits[0].detail["domain_event"] == "CompanyContextUpdated"
    assert audits[0].detail["name_changed"] is True
    assert audits[0].detail["mission_changed"] is False
    assert audits[0].detail["metadata_changed"] is True
    assert "Wisdoverse Cell Public" not in str(audits[0].detail)


@pytest.mark.asyncio
async def test_company_create_rejects_missing_name(db_session: AsyncSession) -> None:
    stores = ControlPlaneStores(db_session)

    with pytest.raises(InvalidCompanyContextError, match="name_required"):
        await create_company_with_audit(
            stores.companies,
            company_id="cmp_company_missing_name",
            name=" ",
            mission="",
            metadata={},
            created_by="human:operator",
        )
