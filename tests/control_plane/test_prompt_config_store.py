"""Tests for the control-plane prompt configuration store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_registry_store import (
    SqlAlchemyControlPlaneAgentRegistryStore,
)
from shared.control_plane.models import AgentRole, CompanyContext
from shared.control_plane.prompt_config_store import (
    SqlAlchemyControlPlanePromptConfigStore,
)


@pytest.mark.asyncio
async def test_prompt_config_store_upserts_prompt_without_losing_metadata(
    db_session: AsyncSession,
):
    registry = SqlAlchemyControlPlaneAgentRegistryStore(db_session)
    store = SqlAlchemyControlPlanePromptConfigStore(db_session)
    company = await store.create_company(CompanyContext(name="Wisdoverse Cell"))
    await registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="requirement-manager",
            display_name="Requirement Manager",
            agent_kind="business_runtime_agent",
            role="product",
        )
    )

    role = await store.get_agent_role(
        company_id=company.company_id,
        agent_id="requirement-manager",
    )
    created = await store.upsert_agent_prompt_config(
        company_id=company.company_id,
        agent_id="requirement-manager",
        system_prompt="Extract requirements.",
        updated_by="human:pm",
        metadata={"source": "initial"},
    )
    updated = await store.upsert_agent_prompt_config(
        company_id=company.company_id,
        agent_id="requirement-manager",
        system_prompt="Extract requirements and risks.",
        updated_by="human:cpo",
    )

    assert role is not None
    assert created.metadata == {"source": "initial"}
    assert not hasattr(created, "metadata_json")
    assert updated.system_prompt == "Extract requirements and risks."
    assert updated.updated_by == "human:cpo"
    assert updated.metadata == {"source": "initial"}
    assert not hasattr(updated, "metadata_json")
