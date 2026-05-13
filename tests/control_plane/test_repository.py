"""Tests for the shared control-plane repository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
    Goal,
    WorkItem,
)
from shared.control_plane.repository import ControlPlaneRepository


@pytest.mark.asyncio
async def test_company_context_can_be_listed_and_updated(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(
            company_id="cmp_wisdoverse",
            name="Wisdoverse Cell",
            mission="Operate with agents",
            metadata={"region": "global"},
        )
    )

    rows = await repo.list_companies(search="wisdoverse")
    updated = await repo.update_company_context(
        company.company_id,
        name="Wisdoverse Cell Public",
        mission="Run AI-native operations",
        metadata={"region": "global", "stage": "public"},
    )

    assert rows[0].company_id == "cmp_wisdoverse"
    assert updated is not None
    assert updated.name == "Wisdoverse Cell Public"
    assert updated.mission == "Run AI-native operations"
    assert updated.metadata_json == {"region": "global", "stage": "public"}


@pytest.mark.asyncio
async def test_create_goal_and_work_item(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    goal = await repo.create_goal(
        Goal(company_id=company.company_id, title="Make SPEC executable")
    )
    work_item = await repo.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Build control-plane ledger",
            external_ref="spec-goal-1",
        )
    )

    fetched_goal = await repo.get_goal(goal.goal_id)
    fetched_work_item = await repo.get_work_item(work_item.work_item_id)

    assert fetched_goal is not None
    assert fetched_goal.title == "Make SPEC executable"
    assert fetched_work_item is not None
    assert fetched_work_item.goal_id == goal.goal_id
    assert fetched_work_item.external_ref == "spec-goal-1"


@pytest.mark.asyncio
async def test_agent_role_can_store_frontend_created_definition(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    role = await repo.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="growth-researcher",
            display_name="Growth Researcher",
            agent_kind="organization_role",
            interaction_mode="direct",
            role="researcher",
            title="Market Research Agent",
            domain="business",
            reports_to_agent_id="ceo",
            adapter_type="codex_local",
            adapter_config={
                "model": "gpt-5.4",
                "cwd": "/workspaces/growth",
            },
            context_sources=["control_plane", "feishu"],
            capabilities=["market analysis", "competitor monitoring"],
            responsibilities=["Find market signals"],
            subscribed_events=["work_item.created", "market.signal-requested"],
            published_events=["market.signal-detected"],
            permissions=["work_items:create"],
            created_by="human:board",
        )
    )

    fetched = await repo.get_agent_role(
        company_id=company.company_id,
        agent_id="growth-researcher",
    )
    rows = await repo.list_agent_roles(
        company_id=company.company_id,
        agent_kind="organization_role",
        adapter_type="codex_local",
        search="growth",
    )

    assert fetched is not None
    assert fetched.role_id == role.role_id
    assert fetched.agent_kind == "organization_role"
    assert fetched.interaction_mode == "direct"
    assert fetched.reports_to_agent_id == "ceo"
    assert fetched.adapter_config["cwd"] == "/workspaces/growth"
    assert fetched.context_sources == ["control_plane", "feishu"]
    assert fetched.capabilities == ["market analysis", "competitor monitoring"]
    assert fetched.subscribed_events == [
        "work_item.created",
        "market.signal-requested",
    ]
    assert fetched.published_events == ["market.signal-detected"]
    assert rows[0].agent_id == "growth-researcher"


@pytest.mark.asyncio
async def test_agent_run_status_transition_records_failure_evidence(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="requirement-manager",
            trace_id="trace_001",
            status=AgentRunStatus.RUNNING,
        )
    )

    updated = await repo.update_agent_run_status(
        run.run_id,
        AgentRunStatus.FAILED,
        error_category="network",
        error_message="provider timeout",
        last_successful_step="validated_input",
    )

    assert updated is not None
    assert updated.status == "failed"
    assert updated.completed_at is not None
    assert updated.error_category == "network"
    assert updated.last_successful_step == "validated_input"


@pytest.mark.asyncio
async def test_agent_run_usage_is_incremental(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="requirement-manager",
            trace_id="trace_001",
            status=AgentRunStatus.RUNNING,
        )
    )

    await repo.add_agent_run_usage(
        run.run_id,
        cost_usd=0.25,
        input_tokens=100,
        output_tokens=40,
    )
    updated = await repo.add_agent_run_usage(
        run.run_id,
        cost_usd=0.75,
        input_tokens=30,
        output_tokens=20,
    )

    assert updated is not None
    assert updated.cost_usd == pytest.approx(1.0)
    assert updated.input_tokens == 130
    assert updated.output_tokens == 60


@pytest.mark.asyncio
async def test_approval_request_can_be_resolved(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    approval = await repo.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:dev-agent",
            source_agent_id="dev-agent",
            proposed_action="Apply migration",
            reason="Control-plane ledger requires durable tables",
            risk="Schema change",
            rollback_note="Downgrade migration drops new ledger tables",
            affected_resources=["postgres"],
        )
    )

    resolved = await repo.resolve_approval(
        approval.approval_id,
        status=ApprovalStatus.APPROVED,
        resolved_by="human:board",
    )

    assert resolved is not None
    assert resolved.status == "approved"
    assert resolved.resolved_by == "human:board"
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_audit_append_is_idempotent_by_key(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    event = AuditEvent(
        company_id=company.company_id,
        action="agent_run.failed",
        target_type="agent_run",
        target_id="run_001",
        trace_id="trace_001",
        idempotency_key="evt_001:requirement-manager",
        detail={"error": "timeout"},
    )

    first = await repo.append_audit_event(event)
    second = await repo.append_audit_event(event)

    assert first.audit_event_id == second.audit_event_id


@pytest.mark.asyncio
async def test_evolution_proposal_lifecycle(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    approval = await repo.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:evolution-module",
            source_agent_id="evolution-module",
            proposed_action="Review L2 evolution proposal",
            reason="Reduce routing latency",
            risk="May change coordination behavior",
            rollback_note="Keep current routing",
            affected_resources=["agent-routing"],
        )
    )
    proposal = await repo.create_evolution_proposal(
        EvolutionProposal(
            company_id=company.company_id,
            tier=EvolutionTier.L2,
            scope="agent-routing",
            evidence={"p95_latency_ms": 1200},
            expected_benefit="Reduce routing latency",
            risk="May change coordination behavior",
            approval_id=approval.approval_id,
        )
    )

    rows = await repo.list_evolution_proposals(
        company_id=company.company_id,
        tier=EvolutionTier.L2.value,
        approval_state=ApprovalStatus.PENDING.value,
    )
    updated = await repo.update_evolution_proposal_status(
        proposal.proposal_id,
        rollout_state=EvolutionRolloutState.SHADOW.value,
    )
    synced = await repo.update_evolution_proposal_approval_state_by_approval(
        approval.approval_id,
        approval_state=ApprovalStatus.APPROVED.value,
    )

    assert rows[0].proposal_id == proposal.proposal_id
    assert updated is not None
    assert updated.rollout_state == EvolutionRolloutState.SHADOW.value
    assert synced is not None
    assert synced.approval_state == ApprovalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_budget_usage_total(db_session: AsyncSession):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(CompanyContext(name="Wisdoverse Cell"))
    budget = await repo.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=25,
        )
    )
    listed = await repo.list_budget_policies(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.DAILY,
        status="active",
    )
    updated = await repo.update_budget_policy(
        budget.budget_id,
        limit_usd=30,
        warning_threshold=0.7,
        model_allowlist=["claude-sonnet-4-20250514"],
    )

    await repo.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=budget.budget_id,
            cost_usd=1.25,
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )
    )
    await repo.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=budget.budget_id,
            cost_usd=0.75,
            model="claude-sonnet-4-20250514",
            input_tokens=20,
            output_tokens=30,
        )
    )

    assert listed[0].budget_id == budget.budget_id
    assert updated is not None
    assert updated.limit_usd == 30
    assert updated.warning_threshold == pytest.approx(0.7)
    assert updated.model_allowlist == ["claude-sonnet-4-20250514"]
    assert await repo.get_budget_usage_total(budget.budget_id) == pytest.approx(2.0)
