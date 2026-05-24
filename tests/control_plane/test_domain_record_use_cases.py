"""Tests for control-plane application-domain return boundaries."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_registry_use_cases import (
    create_agent_role_with_audit,
    get_agent_role,
    list_agent_roles,
)
from shared.control_plane.agent_run_use_cases import get_agent_run, list_agent_runs
from shared.control_plane.api_serialization import row_to_dict
from shared.control_plane.approval_gate import ApprovalGate
from shared.control_plane.approval_use_cases import list_approvals
from shared.control_plane.artifact_use_cases import (
    create_artifact_with_audit,
    list_artifacts,
)
from shared.control_plane.audit_timeline_use_cases import (
    build_timeline,
    list_audit_events,
)
from shared.control_plane.budget_use_cases import (
    create_budget_policy_with_audit,
    list_budget_policies,
    list_budget_usage,
)
from shared.control_plane.company_use_cases import (
    create_company_with_audit,
    list_companies,
)
from shared.control_plane.decision_use_cases import (
    create_decision_with_audit,
    list_decisions,
)
from shared.control_plane.evolution_proposal_use_cases import (
    create_evolution_proposal_with_audit,
    list_evolution_proposals,
)
from shared.control_plane.goal_use_cases import create_goal_with_audit, list_goals
from shared.control_plane.models import (
    AgentInteractionMode,
    AgentKind,
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
    EvolutionProposal,
    EvolutionTier,
    Goal,
    GoalStatus,
    WorkItem,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.work_item_use_cases import (
    create_work_item_with_audit,
    list_work_items,
)


@pytest.mark.asyncio
async def test_operator_use_cases_return_domain_records(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)

    company = await create_company_with_audit(
        stores.companies,
        company_id="cmp_domain_records",
        name="Domain Records Inc.",
        mission="Keep application use cases free of ORM rows",
        metadata={"layer": "application"},
        created_by="architect",
    )
    goal = await create_goal_with_audit(
        stores.goals,
        Goal(
            company_id=company.company_id,
            title="Expose domain records",
            status=GoalStatus.ACTIVE,
            metadata={"record": "goal"},
        ),
        created_by="architect",
    )
    work_item = await create_work_item_with_audit(
        stores.work_items,
        WorkItem(
            company_id=company.company_id,
            title="Verify use-case boundary",
            goal_id=goal.goal_id,
            metadata={"record": "work_item"},
        ),
        created_by="architect",
    )
    decision = await create_decision_with_audit(
        stores.decisions,
        Decision(
            company_id=company.company_id,
            title="Return Pydantic records",
            rationale="Application callers should not receive ORM rows.",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            metadata={"record": "decision"},
        ),
        created_by="architect",
    )
    artifact = await create_artifact_with_audit(
        stores.artifacts,
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="Boundary evidence",
            uri="urn:wisdoverse-cell:control-plane:domain-record-test",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            metadata={"record": "artifact"},
        ),
        created_by="architect",
    )

    companies = await list_companies(stores.companies, search="Domain Records")
    goals = await list_goals(stores.goals, company_id=company.company_id)
    work_items = await list_work_items(
        stores.work_items,
        company_id=company.company_id,
    )
    decisions = await list_decisions(stores.decisions, company_id=company.company_id)
    artifacts = await list_artifacts(stores.artifacts, company_id=company.company_id)

    assert isinstance(company, CompanyContext)
    assert isinstance(companies[0], CompanyContext)
    assert isinstance(goals[0], Goal)
    assert isinstance(work_items[0], WorkItem)
    assert isinstance(decisions[0], Decision)
    assert isinstance(artifacts[0], Artifact)

    assert not hasattr(company, "metadata_json")
    assert not hasattr(goal, "metadata_json")
    assert not hasattr(work_item, "metadata_json")
    assert not hasattr(decision, "metadata_json")
    assert not hasattr(artifact, "metadata_json")

    assert company.metadata == {"layer": "application"}
    assert goal.metadata == {"record": "goal"}
    assert work_item.metadata == {"record": "work_item"}
    assert decision.metadata == {"record": "decision"}
    assert artifact.metadata == {"record": "artifact"}

    payload = row_to_dict(goal)

    assert payload["goal_id"] == goal.goal_id
    assert payload["status"] == GoalStatus.ACTIVE.value
    assert payload["metadata"] == {"record": "goal"}
    assert "metadata_json" not in payload


@pytest.mark.asyncio
async def test_remaining_operator_use_cases_return_domain_records(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    company = await create_company_with_audit(
        stores.companies,
        company_id="cmp_domain_record_batch",
        name="Domain Record Batch",
        mission="Keep every operator use case off ORM rows",
        metadata={},
        created_by="architect",
    )
    agent = await create_agent_role_with_audit(
        stores.agent_registry,
        AgentRole(
            company_id=company.company_id,
            agent_id="domain-record-agent",
            display_name="Domain Record Agent",
            agent_kind=AgentKind.BUSINESS_RUNTIME_AGENT,
            interaction_mode=AgentInteractionMode.DIRECT,
            role="operator",
            title="Boundary Verifier",
            domain="control-plane",
            adapter_type="builtin",
            metadata={"record": "agent_role"},
        ),
    )
    run_row = await stores.agent_runs.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id=agent.agent_id,
            status=AgentRunStatus.RUNNING,
            trace_id="trace_domain_record_batch",
            metadata={"record": "agent_run"},
        )
    )
    budget = await create_budget_policy_with_audit(
        stores.budgets,
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id=agent.agent_id,
            period=BudgetPeriod.DAILY,
            limit_usd=50.0,
            metadata={"record": "budget_policy"},
        ),
        created_by="architect",
    )
    await stores.budgets.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=budget.budget_id,
            cost_usd=1.25,
            model="gpt-5.4",
            run_id=run_row.run_id,
            trace_id="trace_domain_record_batch",
            metadata={"record": "budget_usage"},
        )
    )
    approval = await ApprovalGate(stores.approvals).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:domain-record-agent",
        source_agent_id=agent.agent_id,
        proposed_action="Verify domain-record boundary",
        reason="Architecture batch needs evidence.",
        risk="Low",
        rollback_note="Keep previous ORM-row fallback.",
        affected_resources=["control-plane"],
        trace_id="trace_domain_record_batch",
    )
    proposal = await create_evolution_proposal_with_audit(
        stores.evolution_proposals,
        EvolutionProposal(
            company_id=company.company_id,
            tier=EvolutionTier.L1,
            scope="control-plane-domain-records",
            expected_benefit="Application callers receive domain records.",
            risk="Low",
            metadata={"record": "evolution_proposal"},
        ),
        approval_required=False,
        proposed_by=agent.agent_id,
    )

    listed_agents = await list_agent_roles(
        stores.agent_registry,
        company_id=company.company_id,
        search="Domain Record",
    )
    fetched_agent = await get_agent_role(
        stores.agent_registry,
        company_id=company.company_id,
        agent_id=agent.agent_id,
    )
    listed_runs = await list_agent_runs(
        stores.agent_runs,
        company_id=company.company_id,
        trace_id="trace_domain_record_batch",
    )
    fetched_run = await get_agent_run(stores.agent_runs, run_id=run_row.run_id)
    budget_policies = await list_budget_policies(
        stores.budgets,
        company_id=company.company_id,
    )
    budget_usage = await list_budget_usage(
        stores.budgets,
        company_id=company.company_id,
        trace_id="trace_domain_record_batch",
    )
    approvals = await list_approvals(
        stores.approvals,
        company_id=company.company_id,
        trace_id="trace_domain_record_batch",
    )
    proposals = await list_evolution_proposals(
        stores.evolution_proposals,
        company_id=company.company_id,
    )
    audit_events = await list_audit_events(
        stores.audit_timeline,
        company_id=company.company_id,
    )
    timeline = await build_timeline(
        stores.audit_timeline,
        company_id=company.company_id,
        trace_id="trace_domain_record_batch",
    )

    domain_records = [
        agent,
        listed_agents[0],
        fetched_agent,
        listed_runs[0],
        fetched_run,
        budget,
        budget_policies[0],
        budget_usage[0],
        approval,
        approvals[0],
        proposal,
        proposals[0],
        audit_events[0],
    ]

    assert isinstance(agent, AgentRole)
    assert isinstance(fetched_run, AgentRun)
    assert isinstance(budget_policies[0], BudgetPolicy)
    assert isinstance(budget_usage[0], BudgetUsage)
    assert isinstance(approval, ApprovalRequest)
    assert isinstance(proposals[0], EvolutionProposal)
    assert isinstance(audit_events[0], AuditEvent)
    assert all(not hasattr(record, "metadata_json") for record in domain_records)
    assert {item.item_type for item in timeline} >= {
        "agent_run",
        "approval",
        "budget_usage",
    }
    assert all(not hasattr(item.data, "metadata_json") for item in timeline)

    payload = row_to_dict(fetched_agent)

    assert payload["agent_id"] == agent.agent_id
    assert payload["metadata"] == {"record": "agent_role"}
    assert "metadata_json" not in payload
