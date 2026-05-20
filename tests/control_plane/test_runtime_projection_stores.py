"""Tests for control-plane runtime operation and timeline stores."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_operation_store import (
    SqlAlchemyControlPlaneAgentOperationStore,
)
from shared.control_plane.agent_registry_store import (
    SqlAlchemyControlPlaneAgentRegistryStore,
)
from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.artifact_store import SqlAlchemyControlPlaneArtifactStore
from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.audit_timeline_store import (
    SqlAlchemyControlPlaneAuditTimelineStore,
)
from shared.control_plane.budget_store import SqlAlchemyControlPlaneBudgetStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.decision_store import SqlAlchemyControlPlaneDecisionStore
from shared.control_plane.models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    ApprovalRequest,
    Artifact,
    ArtifactType,
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
    Decision,
)


@pytest.mark.asyncio
async def test_agent_operation_store_composes_runtime_stores(
    db_session: AsyncSession,
):
    registry = SqlAlchemyControlPlaneAgentRegistryStore(db_session)
    store = SqlAlchemyControlPlaneAgentOperationStore(db_session)
    company = await registry.create_company(CompanyContext(name="Wisdoverse Cell"))
    role = await registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="dev-agent",
            display_name="Dev Agent",
            agent_kind="business_runtime_agent",
            role="delivery",
        )
    )
    run = await store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            trace_id="trace_operation_store",
            status=AgentRunStatus.RUNNING,
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=company.company_id,
            action="agent_run.started",
            target_type="agent_run",
            target_id=run.run_id,
            run_id=run.run_id,
        )
    )
    await store.create_artifact(
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="Operation store report",
            uri="s3://wisdoverse-cell/operation-store.md",
            run_id=run.run_id,
            created_by_agent_id="dev-agent",
        )
    )
    completed = await store.update_agent_run_status(
        run.run_id,
        AgentRunStatus.SUCCEEDED,
    )

    fetched_company = await store.get_company(company.company_id)
    fetched_role = await store.get_agent_role(
        company_id=company.company_id,
        agent_id="dev-agent",
    )
    listed_roles = await store.list_agent_roles(
        company_id=company.company_id,
        status="active",
    )

    assert fetched_company is not None
    assert fetched_company.company_id == company.company_id
    assert fetched_role is not None
    assert fetched_role.role_id == role.role_id
    assert [row.role_id for row in listed_roles] == [role.role_id]
    assert completed is not None
    assert completed.status == AgentRunStatus.SUCCEEDED.value
    assert len(
        await store.list_audit_events(
            company_id=company.company_id,
            run_id=run.run_id,
        )
    ) == 1


@pytest.mark.asyncio
async def test_audit_timeline_store_composes_projection_sources(
    db_session: AsyncSession,
):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    runs = SqlAlchemyControlPlaneAgentRunStore(db_session)
    approvals = SqlAlchemyControlPlaneApprovalStore(db_session)
    artifacts = SqlAlchemyControlPlaneArtifactStore(db_session)
    audits = SqlAlchemyControlPlaneAuditEventStore(db_session)
    budgets = SqlAlchemyControlPlaneBudgetStore(db_session)
    decisions = SqlAlchemyControlPlaneDecisionStore(db_session)
    timeline = SqlAlchemyControlPlaneAuditTimelineStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    run = await runs.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="qa-agent",
            trace_id="trace_timeline_store",
            status=AgentRunStatus.RUNNING,
        )
    )
    approval = await approvals.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:qa-agent",
            source_agent_id="qa-agent",
            proposed_action="Run acceptance",
            reason="Timeline evidence",
            risk="None",
            rollback_note="Skip acceptance run",
            affected_resources=["qa"],
            run_id=run.run_id,
            trace_id="trace_timeline_store",
        )
    )
    budget = await budgets.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=10,
        )
    )
    usage = await budgets.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=budget.budget_id,
            cost_usd=0.2,
            model="claude-sonnet-4-20250514",
            run_id=run.run_id,
            trace_id="trace_timeline_store",
        )
    )
    audit = await audits.append_audit_event(
        AuditEvent(
            company_id=company.company_id,
            action="agent_run.started",
            target_type="agent_run",
            target_id=run.run_id,
            run_id=run.run_id,
            trace_id="trace_timeline_store",
        )
    )
    decision = await decisions.create_decision(
        Decision(
            company_id=company.company_id,
            title="Accept rollout",
            rationale="Timeline evidence is complete",
            run_id=run.run_id,
        )
    )
    artifact = await artifacts.create_artifact(
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="Timeline report",
            uri="s3://wisdoverse-cell/timeline.md",
            run_id=run.run_id,
        )
    )

    fetched_run = await timeline.get_agent_run(run.run_id)
    listed_runs = await timeline.list_agent_runs(
        company_id=company.company_id,
        trace_id="trace_timeline_store",
    )
    listed_approvals = await timeline.list_approvals(
        company_id=company.company_id,
        run_id=run.run_id,
        trace_id="trace_timeline_store",
    )
    listed_usage = await timeline.list_budget_usage(
        company_id=company.company_id,
        run_id=run.run_id,
        trace_id="trace_timeline_store",
    )
    listed_audits = await timeline.list_audit_events(
        company_id=company.company_id,
        run_id=run.run_id,
        trace_id="trace_timeline_store",
    )
    listed_decisions = await timeline.list_decisions(
        company_id=company.company_id,
        run_ids=[run.run_id],
    )
    listed_artifacts = await timeline.list_artifacts(
        company_id=company.company_id,
        run_ids=[run.run_id],
    )

    assert fetched_run is not None
    assert fetched_run.run_id == run.run_id
    assert [row.run_id for row in listed_runs] == [run.run_id]
    assert [row.approval_id for row in listed_approvals] == [approval.approval_id]
    assert [row.usage_id for row in listed_usage] == [usage.usage_id]
    assert [row.audit_event_id for row in listed_audits] == [audit.audit_event_id]
    assert [row.decision_id for row in listed_decisions] == [decision.decision_id]
    assert [row.artifact_id for row in listed_artifacts] == [artifact.artifact_id]
