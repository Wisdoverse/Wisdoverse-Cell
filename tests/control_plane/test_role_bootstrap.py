"""Tests for bootstrapping organization-role business agents."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.bootstrap import (
    ensure_core_organization_role_agents,
    ensure_core_runtime_agent_roles,
)
from shared.control_plane.bootstrap_store import SqlAlchemyControlPlaneRoleBootstrapStore
from shared.control_plane.models import AgentKind
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes

CORE_ROLE_AGENT_IDS = {"ceo", "cto", "cpo", "coo"}
CORE_RUNTIME_AGENT_IDS = {
    "analysis-module",
    "channel-gateway",
    "chat-agent",
    "coordinator",
    "dev-agent",
    "evolution-module",
    "pjm-agent",
    "qa-agent",
    "requirement-manager",
    "sync-module",
}


@pytest.mark.asyncio
async def test_bootstrap_creates_core_organization_role_agents(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    store = SqlAlchemyControlPlaneRoleBootstrapStore(db_session)

    created = await ensure_core_organization_role_agents(
        store,
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
    store = SqlAlchemyControlPlaneRoleBootstrapStore(db_session)

    first_created = await ensure_core_organization_role_agents(
        store,
        company_id="cmp_bootstrap_idempotent",
    )
    second_created = await ensure_core_organization_role_agents(
        store,
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


@pytest.mark.asyncio
async def test_bootstrap_creates_configurable_runtime_agent_roles(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    store = SqlAlchemyControlPlaneRoleBootstrapStore(db_session)

    created = await ensure_core_runtime_agent_roles(
        store,
        company_id="cmp_runtime_bootstrap",
        created_by="test-runtime-bootstrap",
    )

    rows = await repo.list_agent_roles(
        company_id="cmp_runtime_bootstrap",
        limit=50,
    )
    runtime_rows = {
        row.agent_id: row
        for row in rows
        if row.metadata_json.get("seed_source") == "core_runtime_modules"
    }
    audits = await repo.list_audit_events(
        company_id="cmp_runtime_bootstrap",
        target_type="agent_role",
        limit=50,
    )

    assert set(created) == CORE_RUNTIME_AGENT_IDS
    assert set(runtime_rows) == CORE_RUNTIME_AGENT_IDS
    assert len(audits) == len(CORE_RUNTIME_AGENT_IDS)

    requirement_manager = runtime_rows["requirement-manager"]
    assert requirement_manager.agent_kind == AgentKind.BUSINESS_RUNTIME_AGENT
    assert requirement_manager.domain == "product"
    assert requirement_manager.reports_to_agent_id == "cpo"
    assert requirement_manager.adapter_type == "builtin"
    assert requirement_manager.adapter_config["execution_mode"] == "runtime_module"
    assert requirement_manager.adapter_config["package_path"] == "agents.requirement_manager"
    assert requirement_manager.metadata_json["business_agent"] is True
    assert requirement_manager.context_sources == [
        "feishu",
        "manual_upload",
        "control_plane",
    ]
    assert "Requirement extraction" in requirement_manager.capabilities
    assert "requirement.confirmed" in requirement_manager.published_events

    qa_agent = runtime_rows["qa-agent"]
    assert qa_agent.agent_kind == AgentKind.BUSINESS_RUNTIME_AGENT
    assert qa_agent.domain == "quality"
    assert qa_agent.reports_to_agent_id == "cto"
    assert "qa.run-requested" in qa_agent.subscribed_events


@pytest.mark.asyncio
async def test_runtime_agent_bootstrap_is_idempotent(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    store = SqlAlchemyControlPlaneRoleBootstrapStore(db_session)

    first_created = await ensure_core_runtime_agent_roles(
        store,
        company_id="cmp_runtime_bootstrap_idempotent",
    )
    second_created = await ensure_core_runtime_agent_roles(
        store,
        company_id="cmp_runtime_bootstrap_idempotent",
    )

    rows = await repo.list_agent_roles(
        company_id="cmp_runtime_bootstrap_idempotent",
        limit=50,
    )
    audits = await repo.list_audit_events(
        company_id="cmp_runtime_bootstrap_idempotent",
        target_type="agent_role",
        limit=50,
    )

    assert set(first_created) == CORE_RUNTIME_AGENT_IDS
    assert second_created == []
    assert {row.agent_id for row in rows} == CORE_RUNTIME_AGENT_IDS
    assert len(rows) == len(CORE_RUNTIME_AGENT_IDS)
    assert len(audits) == len(CORE_RUNTIME_AGENT_IDS)
