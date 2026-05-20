"""Tests for the control-plane agent registry store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_registry_store import (
    SqlAlchemyControlPlaneAgentRegistryStore,
)
from shared.control_plane.models import AgentRole, CompanyContext


@pytest.mark.asyncio
async def test_agent_registry_store_owns_role_lifecycle(db_session: AsyncSession):
    store = SqlAlchemyControlPlaneAgentRegistryStore(db_session)
    company = await store.create_company(CompanyContext(name="Wisdoverse Cell"))
    role = await store.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="growth-researcher",
            display_name="Growth Researcher",
            agent_kind="organization_role",
            interaction_mode="direct",
            role="researcher",
            title="Market Research Agent",
            domain="business",
            adapter_type="codex_local",
            adapter_config={"model": "gpt-5.4"},
            metadata={"seed": "test"},
        )
    )

    listed = await store.list_agent_roles(
        company_id=company.company_id,
        agent_kind="organization_role",
        interaction_mode="direct",
        adapter_type="codex_local",
        search="growth",
    )
    updated = await store.update_agent_role(
        company_id=company.company_id,
        agent_id="growth-researcher",
        values={"metadata": {"seed": "test", "status": "reviewed"}},
    )
    disabled = await store.update_agent_role_status(
        company_id=company.company_id,
        agent_id="growth-researcher",
        status="disabled",
    )

    assert listed[0].role_id == role.role_id
    assert updated is not None
    assert updated.metadata == {"seed": "test", "status": "reviewed"}
    assert not hasattr(updated, "metadata_json")
    assert disabled is not None
    assert disabled.status == "disabled"
