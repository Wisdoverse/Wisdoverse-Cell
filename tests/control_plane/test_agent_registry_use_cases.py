"""Agent registry use-case tests."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_registry_use_cases import (
    update_agent_status_with_audit,
)
from shared.control_plane.domain.agent_role import (
    InvalidAgentRoleStatusError,
    InvalidAgentRoleTransitionError,
)
from shared.control_plane.models import AgentRole, CompanyContext
from shared.control_plane.store_factory import ControlPlaneStores
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_agent_status_update_uses_domain_fsm_and_audit(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_agent_status", name="Agent Status Test")
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="ops-runner",
            display_name="Ops Runner",
        )
    )

    updated = await update_agent_status_with_audit(
        stores.agent_registry,
        company_id=company.company_id,
        agent_id="ops-runner",
        status="paused",
        actor_id="human:operator",
    )
    audits = await stores.audit_events.list_audit_events(
        company_id=company.company_id,
        target_type="agent_role",
    )

    assert updated.status == "paused"
    assert len(audits) == 1
    assert audits[0].action == EventTypes.AGENT_ROLE_STATUS_UPDATED
    assert audits[0].detail["domain_event"] == "AgentRoleStatusChanged"
    assert audits[0].detail["from_status"] == "active"
    assert audits[0].detail["to_status"] == "paused"


@pytest.mark.asyncio
async def test_agent_status_update_rejects_unknown_status(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_agent_unknown_status", name="Agent Status Test")
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="ops-runner",
            display_name="Ops Runner",
        )
    )

    with pytest.raises(InvalidAgentRoleStatusError):
        await update_agent_status_with_audit(
            stores.agent_registry,
            company_id=company.company_id,
            agent_id="ops-runner",
            status="custom",
            actor_id="human:operator",
        )


@pytest.mark.asyncio
async def test_agent_status_update_rejects_terminal_reactivation(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_agent_terminal_status", name="Agent Status Test")
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="ops-runner",
            display_name="Ops Runner",
            status="terminated",
        )
    )

    with pytest.raises(InvalidAgentRoleTransitionError):
        await update_agent_status_with_audit(
            stores.agent_registry,
            company_id=company.company_id,
            agent_id="ops-runner",
            status="active",
            actor_id="human:operator",
        )
