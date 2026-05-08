"""Tests for bootstrapping organization-role business agents."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.bootstrap import ensure_core_organization_role_agents
from shared.control_plane.models import AgentKind
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes

CORE_ROLE_AGENT_IDS = {"ceo", "cto", "cpo", "coo"}


@pytest.mark.asyncio
async def test_bootstrap_creates_core_organization_role_agents(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)

    created = await ensure_core_organization_role_agents(
        repo,
        company_id="cmp_bootstrap",
        created_by="test-bootstrap",
    )

    rows = await repo.list_agent_roles(
        company_id="cmp_bootstrap",
        agent_kind=AgentKind.ORGANIZATION_ROLE,
        limit=20,
    )
    roles_by_id = {row.agent_id: row for row in rows}
    audits = await repo.list_audit_events(
        company_id="cmp_bootstrap",
        target_type="agent_role",
        limit=20,
    )

    assert set(created) == CORE_ROLE_AGENT_IDS
    assert set(roles_by_id) == CORE_ROLE_AGENT_IDS
    assert len(audits) == 4
    for agent_id, row in roles_by_id.items():
        assert row.display_name in {"CEO", "CTO", "CPO", "COO"}
        assert row.agent_kind == AgentKind.ORGANIZATION_ROLE
        assert row.adapter_type == "builtin"
        assert row.status == "active"
        assert row.created_by == "test-bootstrap"
        assert row.metadata_json["business_agent"] is True
        assert row.context_sources[:2] == ["control_plane", "operator_console"]
        assert row.capabilities
        assert row.responsibilities
        assert row.subscribed_events
        assert row.published_events
        if agent_id == "ceo":
            assert row.reports_to_agent_id is None
        else:
            assert row.reports_to_agent_id == "ceo"

    ceo = roles_by_id["ceo"]
    cto = roles_by_id["cto"]
    assert EventTypes.BUDGET_USAGE_RECORDED in ceo.subscribed_events
    assert "analysis.risk-detected" in ceo.subscribed_events
    assert "qa.gate-failed" in cto.subscribed_events
    assert EventTypes.DECISION_CREATED in cto.published_events


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)

    first_created = await ensure_core_organization_role_agents(
        repo,
        company_id="cmp_bootstrap_idempotent",
    )
    second_created = await ensure_core_organization_role_agents(
        repo,
        company_id="cmp_bootstrap_idempotent",
    )

    rows = await repo.list_agent_roles(
        company_id="cmp_bootstrap_idempotent",
        agent_kind=AgentKind.ORGANIZATION_ROLE,
        limit=20,
    )
    audits = await repo.list_audit_events(
        company_id="cmp_bootstrap_idempotent",
        target_type="agent_role",
        limit=20,
    )

    assert set(first_created) == CORE_ROLE_AGENT_IDS
    assert second_created == []
    assert {row.agent_id for row in rows} == CORE_ROLE_AGENT_IDS
    assert len(rows) == 4
    assert len(audits) == 4
