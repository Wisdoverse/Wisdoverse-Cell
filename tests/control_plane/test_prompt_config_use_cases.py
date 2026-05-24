"""Prompt-configuration use-case tests."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_prompt_config import update_prompt_config_with_audit
from shared.control_plane.domain.agent_prompt_config import InvalidAgentPromptConfigError
from shared.control_plane.models import AgentRole, CompanyContext
from shared.control_plane.store_factory import ControlPlaneStores
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_prompt_config_update_uses_domain_policy_and_audit(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_prompt_domain", name="Prompt Domain Test")
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="requirement-manager",
            display_name="Requirement Manager",
        )
    )

    result = await update_prompt_config_with_audit(
        stores.prompt_configs,
        company_id=company.company_id,
        agent_id="requirement-manager",
        system_prompt="  Extract requirements.  ",
        updated_by="  human:pm  ",
        metadata={"source": "operator"},
    )
    audits = await stores.audit_events.list_audit_events(
        company_id=company.company_id,
        target_type="agent_prompt_config",
    )

    assert result["system_prompt"] == "Extract requirements."
    assert result["updated_by"] == "human:pm"
    assert result["metadata"] == {"source": "operator"}
    assert len(audits) == 1
    assert audits[0].action == EventTypes.AGENT_PROMPT_CONFIG_UPDATED
    assert audits[0].actor_id == "human:pm"
    assert audits[0].detail["domain_event"] == "AgentPromptConfigUpdated"
    assert audits[0].detail["prompt_length"] == len("Extract requirements.")
    assert audits[0].detail["metadata_keys"] == ["source"]
    assert "Extract requirements" not in str(audits[0].detail)


@pytest.mark.asyncio
async def test_prompt_config_update_rejects_too_long_prompt(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(company_id="cmp_prompt_too_long", name="Prompt Domain Test")
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="requirement-manager",
            display_name="Requirement Manager",
        )
    )

    with pytest.raises(InvalidAgentPromptConfigError, match="system_prompt_too_long"):
        await update_prompt_config_with_audit(
            stores.prompt_configs,
            company_id=company.company_id,
            agent_id="requirement-manager",
            system_prompt="x" * 50_001,
            updated_by="human:pm",
            metadata={},
        )
