"""Tests for the control-plane operator API router."""

import sys
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api import create_control_plane_router
from shared.control_plane.models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    ApprovalRequest,
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
)
from shared.control_plane.repository import ControlPlaneRepository
from shared.middleware import internal_auth as _internal_auth_mod
from shared.schemas.event import EventTypes


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider():
        yield db_session
        await db_session.flush()

    return _provider


async def _seed(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_api", name="API Test")
    )
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace-api",
        )
    )
    approval = await repo.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:dev-agent",
            source_agent_id="dev-agent",
            proposed_action="Run workflow",
            reason="High risk task",
            risk="External workflow execution",
            rollback_note="Cancel workflow",
            affected_resources=["agentforge:workflow"],
            run_id=run.run_id,
            trace_id="trace-api",
        )
    )
    budget = await repo.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=5.0,
        )
    )
    await repo.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=budget.budget_id,
            cost_usd=0.25,
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=20,
            run_id=run.run_id,
            trace_id="trace-api",
        )
    )
    await repo.append_audit_event(
        AuditEvent(
            company_id=company.company_id,
            action="agent_run.started",
            target_type="agent_run",
            target_id=run.run_id,
            actor_type="agent",
            actor_id="dev-agent",
            run_id=run.run_id,
            trace_id="trace-api",
            detail={"event_type": "work.execute"},
        )
    )
    await db_session.flush()
    return run, approval


@pytest.mark.asyncio
async def test_control_plane_api_manages_company_contexts(db_session: AsyncSession):
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/control-plane/companies",
            json={
                "company_id": "cmp_public",
                "name": "Wisdoverse Cell",
                "mission": "Operate with agents",
                "metadata": {"stage": "public"},
                "created_by": "human:operator",
            },
        )
        duplicate = await client.post(
            "/api/v1/control-plane/companies",
            json={
                "company_id": "cmp_public",
                "name": "Wisdoverse Cell",
            },
        )
        listed = await client.get(
            "/api/v1/control-plane/companies",
            params={"search": "wisdoverse"},
        )
        fetched = await client.get("/api/v1/control-plane/companies/cmp_public")
        updated = await client.patch(
            "/api/v1/control-plane/companies/cmp_public",
            json={
                "mission": "Run AI-native operations",
                "metadata": {"stage": "public", "region": "global"},
                "actor_id": "human:operator",
            },
        )
        missing = await client.get("/api/v1/control-plane/companies/cmp_missing")
        audit = await client.get(
            "/api/v1/control-plane/audit-events",
            params={"company_id": "cmp_public", "target_type": "company"},
        )

    assert created.status_code == 201
    assert created.json()["company_id"] == "cmp_public"
    assert created.json()["metadata"] == {"stage": "public"}
    assert duplicate.status_code == 409
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Wisdoverse Cell"
    assert updated.status_code == 200
    assert updated.json()["mission"] == "Run AI-native operations"
    assert updated.json()["metadata"] == {"stage": "public", "region": "global"}
    assert missing.status_code == 404
    assert audit.status_code == 200
    assert [event["action"] for event in audit.json()["audit_events"]] == [
        EventTypes.COMPANY_UPDATED,
        EventTypes.COMPANY_CREATED,
    ]


@pytest.mark.asyncio
async def test_control_plane_api_manages_evolution_proposals(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(CompanyContext(company_id="cmp_evolution", name="Evolution"))
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/control-plane/evolution-proposals",
            json={
                "company_id": "cmp_evolution",
                "tier": "L2",
                "scope": "agent-routing",
                "evidence": {"p95_latency_ms": 1200},
                "expected_benefit": "Reduce routing latency",
                "risk": "May change coordinator dispatch behavior",
                "proposed_by": "evolution-module",
            },
        )
        proposal = created.json()
        listed = await client.get(
            "/api/v1/control-plane/evolution-proposals",
            params={"company_id": "cmp_evolution", "tier": "L2"},
        )
        blocked = await client.patch(
            f"/api/v1/control-plane/evolution-proposals/{proposal['proposal_id']}/status",
            params={"company_id": "cmp_evolution"},
            json={"rollout_state": "active", "actor_id": "human:architect"},
        )
        approved = await client.post(
            f"/api/v1/control-plane/approvals/{proposal['approval_id']}/approve",
            json={"resolved_by": "human:architect"},
        )
        fetched_after_approval = await client.get(
            f"/api/v1/control-plane/evolution-proposals/{proposal['proposal_id']}",
            params={"company_id": "cmp_evolution"},
        )
        activated = await client.patch(
            f"/api/v1/control-plane/evolution-proposals/{proposal['proposal_id']}/status",
            params={"company_id": "cmp_evolution"},
            json={"rollout_state": "active", "actor_id": "human:architect"},
        )

    assert created.status_code == 201
    assert proposal["approval_state"] == "pending"
    assert proposal["rollout_state"] == "proposed"
    assert proposal["approval_id"]
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "approval_required"
    assert approved.status_code == 200
    assert fetched_after_approval.status_code == 200
    assert fetched_after_approval.json()["approval_state"] == "approved"
    assert activated.status_code == 200
    assert activated.json()["rollout_state"] == "active"


@pytest.mark.asyncio
async def test_control_plane_api_lists_approves_and_builds_timeline(
    db_session: AsyncSession,
):
    run, approval = await _seed(db_session)
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_api"},
        )
        approvals = await client.get(
            "/api/v1/control-plane/approvals",
            params={"company_id": "cmp_api", "status": "pending"},
        )
        approved = await client.post(
            f"/api/v1/control-plane/approvals/{approval.approval_id}/approve",
            json={"resolved_by": "human:lead"},
        )
        timeline = await client.get(
            "/api/v1/control-plane/timeline",
            params={"company_id": "cmp_api", "run_id": run.run_id},
        )

    assert runs.status_code == 200
    assert runs.json()["runs"][0]["run_id"] == run.run_id
    assert approvals.status_code == 200
    assert approvals.json()["approvals"][0]["approval_id"] == approval.approval_id
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert timeline.status_code == 200
    item_types = {item["type"] for item in timeline.json()["timeline"]}
    assert {"approval", "audit_event", "budget_usage"}.issubset(item_types)


@pytest.mark.asyncio
async def test_control_plane_api_manages_goals_and_work_items(
    db_session: AsyncSession,
):
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created_goal = await client.post(
            "/api/v1/control-plane/goals",
            json={
                "company_id": "cmp_goal_api",
                "title": "Ship SPEC control plane",
                "description": "Make goals and work visible",
                "status": "active",
                "owner_agent_id": "pjm-agent",
                "success_metric": "P0 ledger surfaces available",
                "target_value": 100,
                "current_value": 10,
                "tags": ["spec", "p0"],
                "created_by": "human:board",
            },
        )
        goal_id = created_goal.json()["goal_id"]
        listed_goals = await client.get(
            "/api/v1/control-plane/goals",
            params={"company_id": "cmp_goal_api", "status": "active", "search": "SPEC"},
        )
        updated_goal = await client.patch(
            f"/api/v1/control-plane/goals/{goal_id}/status",
            params={"company_id": "cmp_goal_api"},
            json={
                "status": "completed",
                "current_value": 100,
                "actor_id": "human:board",
            },
        )
        created_work = await client.post(
            "/api/v1/control-plane/work-items",
            json={
                "company_id": "cmp_goal_api",
                "title": "Expose goal API",
                "description": "Create/list/get/status endpoints",
                "status": "ready",
                "priority": "high",
                "goal_id": goal_id,
                "owner_agent_id": "dev-agent",
                "external_ref": "spec-goal-api",
                "created_by": "human:board",
            },
        )
        work_item_id = created_work.json()["work_item_id"]
        listed_work = await client.get(
            "/api/v1/control-plane/work-items",
            params={
                "company_id": "cmp_goal_api",
                "goal_id": goal_id,
                "priority": "high",
            },
        )
        updated_work = await client.patch(
            f"/api/v1/control-plane/work-items/{work_item_id}/status",
            params={"company_id": "cmp_goal_api"},
            json={
                "status": "running",
                "owner_agent_id": "dev-agent",
                "actor_id": "human:board",
            },
        )
        audits = await client.get(
            "/api/v1/control-plane/audit-events",
            params={"company_id": "cmp_goal_api", "target_type": "work_item"},
        )

    assert created_goal.status_code == 201
    assert created_goal.json()["status"] == "active"
    assert listed_goals.status_code == 200
    assert listed_goals.json()["total"] == 1
    assert updated_goal.status_code == 200
    assert updated_goal.json()["status"] == "completed"
    assert updated_goal.json()["current_value"] == 100
    assert created_work.status_code == 201
    assert created_work.json()["goal_id"] == goal_id
    assert listed_work.status_code == 200
    assert listed_work.json()["work_items"][0]["work_item_id"] == work_item_id
    assert updated_work.status_code == 200
    assert updated_work.json()["status"] == "running"
    assert audits.status_code == 200
    assert {item["action"] for item in audits.json()["audit_events"]} == {
        EventTypes.WORK_ITEM_CREATED,
        EventTypes.WORK_ITEM_UPDATED,
    }


@pytest.mark.asyncio
async def test_control_plane_api_rejects_work_item_with_missing_goal(
    db_session: AsyncSession,
):
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/control-plane/work-items",
            json={
                "company_id": "cmp_goal_api",
                "title": "Bad work item",
                "goal_id": "goal_missing",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "goal_not_found"


@pytest.mark.asyncio
async def test_control_plane_api_manages_decisions_artifacts_and_timeline(
    db_session: AsyncSession,
):
    run, _approval = await _seed(db_session)
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created_goal = await client.post(
            "/api/v1/control-plane/goals",
            json={"company_id": "cmp_api", "title": "Decision lineage"},
        )
        goal_id = created_goal.json()["goal_id"]
        created_work = await client.post(
            "/api/v1/control-plane/work-items",
            json={
                "company_id": "cmp_api",
                "title": "Produce handoff",
                "goal_id": goal_id,
            },
        )
        work_item_id = created_work.json()["work_item_id"]
        decision = await client.post(
            "/api/v1/control-plane/decisions",
            json={
                "company_id": "cmp_api",
                "title": "Proceed with handoff",
                "rationale": "QA passed and risk is acceptable",
                "run_id": run.run_id,
                "work_item_id": work_item_id,
                "goal_id": goal_id,
                "options": [{"id": "ship", "label": "Ship"}],
                "created_by": "human:lead",
            },
        )
        decision_id = decision.json()["decision_id"]
        accepted = await client.patch(
            f"/api/v1/control-plane/decisions/{decision_id}/status",
            params={"company_id": "cmp_api"},
            json={
                "status": "accepted",
                "selected_option": "ship",
                "decided_by": "human:lead",
                "actor_id": "human:lead",
            },
        )
        artifact = await client.post(
            "/api/v1/control-plane/artifacts",
            json={
                "company_id": "cmp_api",
                "artifact_type": "report",
                "title": "Run handoff",
                "uri": "artifact://runs/handoff",
                "run_id": run.run_id,
                "work_item_id": work_item_id,
                "goal_id": goal_id,
                "created_by_agent_id": "dev-agent",
                "created_by": "agent:dev-agent",
            },
        )
        artifacts = await client.get(
            "/api/v1/control-plane/artifacts",
            params={"company_id": "cmp_api", "run_id": run.run_id},
        )
        timeline = await client.get(
            "/api/v1/control-plane/timeline",
            params={"company_id": "cmp_api", "run_id": run.run_id},
        )

    assert decision.status_code == 201
    assert decision.json()["work_item_id"] == work_item_id
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["selected_option"] == "ship"
    assert artifact.status_code == 201
    assert artifact.json()["goal_id"] == goal_id
    assert artifacts.status_code == 200
    assert artifacts.json()["artifacts"][0]["artifact_id"] == artifact.json()["artifact_id"]
    assert timeline.status_code == 200
    assert {"agent_run", "approval", "audit_event", "artifact", "decision"}.issubset(
        {item["type"] for item in timeline.json()["timeline"]}
    )


@pytest.mark.asyncio
async def test_control_plane_api_creates_frontend_agent_definition(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(CompanyContext(company_id="cmp_agents", name="Agent API Test"))
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agents",
                "agent_id": "growth-researcher",
                "display_name": "Growth Researcher",
                "agent_kind": "organization_role",
                "interaction_mode": "direct",
                "role": "researcher",
                "title": "Market Research Agent",
                "domain": "business",
                "reports_to_agent_id": "ceo",
                "adapter_type": "codex_local",
                "adapter_config": {
                    "model": "gpt-5.4",
                    "cwd": "/workspaces/growth",
                },
                "context_sources": ["control_plane", "feishu"],
                "capabilities": ["market analysis"],
                "responsibilities": ["Find market signals"],
                "subscribed_events": [
                    "work_item.created",
                    "market.signal-requested",
                ],
                "published_events": ["market.signal-detected"],
                "permissions": ["work_items:create"],
                "created_by": "human:board",
            },
        )
        duplicate = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agents",
                "agent_id": "growth-researcher",
                "display_name": "Growth Researcher",
            },
        )
        listed = await client.get(
            "/api/v1/control-plane/agents",
            params={"company_id": "cmp_agents", "search": "growth"},
        )
        status = await client.patch(
            "/api/v1/control-plane/agents/growth-researcher/status",
            params={"company_id": "cmp_agents"},
            json={"status": "paused", "actor_id": "human:board"},
        )

    assert created.status_code == 201
    assert created.json()["agent_id"] == "growth-researcher"
    assert created.json()["agent_kind"] == "organization_role"
    assert created.json()["interaction_mode"] == "direct"
    assert created.json()["adapter_type"] == "codex_local"
    assert created.json()["context_sources"] == ["control_plane", "feishu"]
    assert created.json()["subscribed_events"] == [
        "work_item.created",
        "market.signal-requested",
    ]
    assert created.json()["published_events"] == ["market.signal-detected"]
    assert duplicate.status_code == 409
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["agents"][0]["reports_to_agent_id"] == "ceo"
    assert listed.json()["agents"][0]["subscribed_events"] == [
        "work_item.created",
        "market.signal-requested",
    ]
    assert status.status_code == 200
    assert status.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_control_plane_api_manages_agent_prompt_config(
    db_session: AsyncSession,
):
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        initial = await client.get(
            "/api/v1/control-plane/agents/requirement-manager/prompt-config",
            params={"company_id": "cmp_prompt"},
        )
        saved = await client.put(
            "/api/v1/control-plane/agents/requirement-manager/prompt-config",
            params={"company_id": "cmp_prompt"},
            json={
                "system_prompt": "Operate as the requirement intake owner.",
                "updated_by": "human:operator",
                "metadata": {"source": "test"},
            },
        )
        fetched = await client.get(
            "/api/v1/control-plane/agents/requirement-manager/prompt-config",
            params={"company_id": "cmp_prompt"},
        )
        missing = await client.put(
            "/api/v1/control-plane/agents/not-a-real-agent/prompt-config",
            params={"company_id": "cmp_prompt"},
            json={"system_prompt": "Nope"},
        )
        audit = await client.get(
            "/api/v1/control-plane/audit-events",
            params={
                "company_id": "cmp_prompt",
                "target_type": "agent_prompt_config",
            },
        )

    assert initial.status_code == 200
    assert initial.json()["system_prompt"] == ""
    assert saved.status_code == 200
    assert saved.json()["system_prompt"] == "Operate as the requirement intake owner."
    assert saved.json()["updated_by"] == "human:operator"
    assert saved.json()["metadata"] == {"source": "test"}
    assert fetched.status_code == 200
    assert fetched.json()["system_prompt"] == saved.json()["system_prompt"]
    assert missing.status_code == 404
    assert audit.status_code == 200
    events = audit.json()["audit_events"]
    assert events[0]["action"] == EventTypes.AGENT_PROMPT_CONFIG_UPDATED
    assert events[0]["detail"]["prompt_length"] == len(saved.json()["system_prompt"])
    assert saved.json()["system_prompt"] not in str(events[0]["detail"])


@pytest.mark.asyncio
async def test_control_plane_api_separates_agent_kinds(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(CompanyContext(company_id="cmp_agent_kinds", name="Kinds"))
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        role_agent = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agent_kinds",
                "agent_id": "cto",
                "display_name": "CTO",
                "agent_kind": "organization_role",
                "interaction_mode": "direct",
                "role": "cto",
                "title": "Chief Technology Officer",
                "domain": "engineering",
                "context_sources": ["control_plane", "gitlab"],
            },
        )
        module_agent = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agent_kinds",
                "agent_id": "sync-module",
                "display_name": "Sync Module",
                "agent_kind": "capability_module",
                "interaction_mode": "internal",
                "role": "sync-capability",
                "title": "Context Sync Module",
                "domain": "operations",
                "context_sources": ["openproject", "feishu"],
            },
        )
        business_runtime_agent = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agent_kinds",
                "agent_id": "qa-agent",
                "display_name": "QA Agent",
                "agent_kind": "business_runtime_agent",
                "interaction_mode": "internal",
                "role": "quality-agent",
                "title": "QA Agent",
                "domain": "quality",
                "context_sources": ["gitlab", "control_plane"],
            },
        )
        invalid_module = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_agent_kinds",
                "agent_id": "qa-direct",
                "display_name": "QA Direct",
                "agent_kind": "business_runtime_agent",
                "interaction_mode": "direct",
            },
        )
        listed_roles = await client.get(
            "/api/v1/control-plane/agents",
            params={"company_id": "cmp_agent_kinds", "agent_kind": "organization_role"},
        )
        listed_modules = await client.get(
            "/api/v1/control-plane/agents",
            params={"company_id": "cmp_agent_kinds", "agent_kind": "capability_module"},
        )
        listed_business_agents = await client.get(
            "/api/v1/control-plane/agents",
            params={
                "company_id": "cmp_agent_kinds",
                "agent_kind": "business_runtime_agent",
            },
        )

    assert role_agent.status_code == 201
    assert module_agent.status_code == 201
    assert business_runtime_agent.status_code == 201
    assert invalid_module.status_code == 422
    assert listed_roles.json()["total"] == 1
    assert listed_roles.json()["agents"][0]["agent_id"] == "cto"
    assert listed_modules.json()["total"] == 1
    assert listed_modules.json()["agents"][0]["agent_kind"] == "capability_module"
    assert listed_business_agents.json()["total"] == 1
    assert (
        listed_business_agents.json()["agents"][0]["agent_kind"]
        == "business_runtime_agent"
    )


@pytest.mark.asyncio
async def test_control_plane_api_wakes_process_agent_definition(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_enabled",
        True,
    )
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_allowlist",
        "process:ops-runner",
    )
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(CompanyContext(company_id="cmp_wake", name="Wake Test"))
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_wake",
                "agent_id": "ops-runner",
                "display_name": "Ops Runner",
                "adapter_type": "process",
                "adapter_config": {
                    "command": [
                        sys.executable,
                        "-c",
                        "import json,sys; data=json.load(sys.stdin); print(data['agent_id'])",
                    ],
                    "timeout_sec": 10,
                },
            },
        )
        wake = await client.post(
            "/api/v1/control-plane/agents/ops-runner/wake",
            json={
                "company_id": "cmp_wake",
                "actor_id": "human:board",
                "trace_id": "trace-wake",
                "input": {"task": "check"},
            },
        )
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_wake", "agent_id": "ops-runner"},
        )
        timeline = await client.get(
            "/api/v1/control-plane/timeline",
            params={"company_id": "cmp_wake", "run_id": wake.json()["run"]["run_id"]},
        )

    assert wake.status_code == 200
    assert wake.json()["run"]["status"] == "succeeded"
    assert wake.json()["output"]["stdout"].strip() == "ops-runner"
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["trace_id"] == "trace-wake"
    assert runs.json()["runs"][0]["input_event"]["event_type"] == (
        EventTypes.AGENT_WAKEUP_REQUESTED
    )
    assert runs.json()["runs"][0]["input_event"]["payload"]["trace_id"] == "trace-wake"
    assert runs.json()["runs"][0]["input_event"]["metadata"]["trace_id"] == "trace-wake"
    assert runs.json()["runs"][0]["output_events"][0]["event_type"] == (
        EventTypes.AGENT_WAKEUP_COMPLETED
    )
    assert runs.json()["runs"][0]["output_events"][0]["payload"]["trace_id"] == (
        "trace-wake"
    )
    assert runs.json()["runs"][0]["output_events"][0]["metadata"]["trace_id"] == (
        "trace-wake"
    )
    assert runs.json()["runs"][0]["output_events"][0]["payload"]["run_id"] == (
        wake.json()["run"]["run_id"]
    )
    assert timeline.status_code == 200
    assert {"audit_event"}.issubset(
        {item["type"] for item in timeline.json()["timeline"]}
    )


@pytest.mark.asyncio
async def test_control_plane_service_actions_require_internal_key(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(CompanyContext(company_id="cmp_internal", name="Internal"))
    await repo.create_agent_role(
        AgentRole(
            company_id="cmp_internal",
            agent_id="internal-runner",
            display_name="Internal Runner",
            adapter_type="builtin",
        )
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    with patch.object(_internal_auth_mod, "settings") as mock_settings:
        mock_settings.internal_service_key = "secret-key"
        mock_settings.app_env = "development"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing_wake = await client.post(
                "/api/v1/control-plane/agents/internal-runner/wake",
                json={"company_id": "cmp_internal"},
            )
            missing_scheduler = await client.post(
                "/api/v1/control-plane/scheduler/heartbeats/run-once",
                json={"company_id": "cmp_internal"},
            )
            allowed_wake = await client.post(
                "/api/v1/control-plane/agents/internal-runner/wake",
                json={"company_id": "cmp_internal"},
                headers={"X-Internal-Key": "secret-key"},
            )
            allowed_scheduler = await client.post(
                "/api/v1/control-plane/scheduler/heartbeats/run-once",
                json={"company_id": "cmp_internal"},
                headers={"X-Internal-Key": "secret-key"},
            )

    assert missing_wake.status_code == 401
    assert missing_scheduler.status_code == 401
    assert allowed_wake.status_code == 200
    assert allowed_scheduler.status_code == 200


@pytest.mark.asyncio
async def test_control_plane_api_runs_due_heartbeat_scheduler(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(
        CompanyContext(company_id="cmp_heartbeat", name="Heartbeat Test")
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_heartbeat",
                "agent_id": "heartbeat-runner",
                "display_name": "Heartbeat Runner",
                "adapter_type": "builtin",
                "adapter_config": {
                    "heartbeat_enabled": True,
                    "heartbeat_interval_seconds": 60,
                },
            },
        )
        scheduled = await client.post(
            "/api/v1/control-plane/scheduler/heartbeats/run-once",
            json={"company_id": "cmp_heartbeat"},
        )
        repeated = await client.post(
            "/api/v1/control-plane/scheduler/heartbeats/run-once",
            json={"company_id": "cmp_heartbeat"},
        )
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_heartbeat", "agent_id": "heartbeat-runner"},
        )
        run_id = scheduled.json()["results"][0]["run_id"]
        audits = await client.get(
            "/api/v1/control-plane/audit-events",
            params={"company_id": "cmp_heartbeat", "run_id": run_id},
        )

    assert created.status_code == 201
    assert scheduled.status_code == 200
    assert scheduled.json()["total"] == 1
    assert scheduled.json()["results"][0]["status"] == "succeeded"
    assert scheduled.json()["results"][0]["agent_id"] == "heartbeat-runner"
    assert repeated.status_code == 200
    assert repeated.json()["results"][0]["status"] == "skipped"
    assert repeated.json()["results"][0]["skipped_reason"] == "interval_not_elapsed"
    assert runs.status_code == 200
    assert len(runs.json()["runs"]) == 1
    run = runs.json()["runs"][0]
    assert run["trigger_event_id"].startswith("evt_")
    assert run["input_event"]["event_id"] == run["trigger_event_id"]
    assert run["input_event"]["metadata"]["trace_id"] == run["trace_id"]
    assert run["output_events"][0]["metadata"]["trace_id"] == run["trace_id"]
    assert run["input_event"]["payload"]["input"]["trigger"] == "heartbeat"
    assert run["input_event"]["payload"]["actor_id"] == "control-plane:scheduler"
    assert audits.status_code == 200
    audit_details = {item["action"]: item["detail"] for item in audits.json()["audit_events"]}
    assert audit_details[EventTypes.AGENT_RUN_STARTED]["trigger"] == (
        "scheduled_heartbeat"
    )
    assert audit_details[EventTypes.AGENT_RUN_SUCCEEDED]["trigger"] == (
        "scheduled_heartbeat"
    )


@pytest.mark.asyncio
async def test_control_plane_heartbeat_scheduler_skips_agents_without_opt_in(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(
        CompanyContext(company_id="cmp_no_heartbeat", name="No Heartbeat Test")
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_no_heartbeat",
                "agent_id": "manual-only",
                "display_name": "Manual Only",
                "adapter_type": "builtin",
            },
        )
        scheduled = await client.post(
            "/api/v1/control-plane/scheduler/heartbeats/run-once",
            json={"company_id": "cmp_no_heartbeat"},
        )
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_no_heartbeat", "agent_id": "manual-only"},
        )

    assert scheduled.status_code == 200
    assert scheduled.json()["total"] == 0
    assert scheduled.json()["results"] == []
    assert runs.json()["runs"] == []


@pytest.mark.asyncio
async def test_control_plane_api_blocks_local_adapter_by_default(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(
        CompanyContext(company_id="cmp_wake_blocked", name="Wake Blocked Test")
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_wake_blocked",
                "agent_id": "local-runner",
                "display_name": "Local Runner",
                "adapter_type": "process",
                "adapter_config": {"command": [sys.executable, "-c", "print('no')"]},
            },
        )
        wake = await client.post(
            "/api/v1/control-plane/agents/local-runner/wake",
            json={"company_id": "cmp_wake_blocked"},
        )
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_wake_blocked", "agent_id": "local-runner"},
        )

    assert wake.status_code == 403
    assert wake.json()["detail"] == "local_adapter_disabled"
    assert runs.json()["runs"][0]["status"] == "failed"
    assert runs.json()["runs"][0]["error_category"] == "adapter_disabled"


@pytest.mark.asyncio
async def test_control_plane_api_blocks_enabled_local_adapter_without_allowlist(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_enabled",
        True,
    )
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_allowlist",
        "",
    )
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(
        CompanyContext(company_id="cmp_wake_not_allowed", name="Wake Not Allowed Test")
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_wake_not_allowed",
                "agent_id": "local-runner",
                "display_name": "Local Runner",
                "adapter_type": "process",
                "adapter_config": {"command": [sys.executable, "-c", "print('no')"]},
            },
        )
        wake = await client.post(
            "/api/v1/control-plane/agents/local-runner/wake",
            json={"company_id": "cmp_wake_not_allowed"},
        )
        runs = await client.get(
            "/api/v1/control-plane/runs",
            params={"company_id": "cmp_wake_not_allowed", "agent_id": "local-runner"},
        )

    assert wake.status_code == 403
    assert wake.json()["detail"] == "local_adapter_not_allowlisted"
    assert runs.json()["runs"][0]["status"] == "failed"
    assert runs.json()["runs"][0]["error_category"] == "adapter_not_allowlisted"


@pytest.mark.asyncio
async def test_control_plane_api_rejects_unknown_adapter_definition(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    await repo.create_company(
        CompanyContext(company_id="cmp_unknown_adapter", name="Unknown Adapter Test")
    )
    app = FastAPI()
    app.include_router(
        create_control_plane_router(session_provider=_session_provider(db_session))
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/control-plane/agents",
            json={
                "company_id": "cmp_unknown_adapter",
                "agent_id": "unknown-runner",
                "display_name": "Unknown Runner",
                "adapter_type": "shell_eval",
            },
        )

    assert created.status_code == 400
    assert created.json()["detail"] == "unsupported_adapter_type"
