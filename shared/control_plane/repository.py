"""Compatibility repository facade for the shared control-plane ledger."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .agent_registry_store import SqlAlchemyControlPlaneAgentRegistryStore
from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .artifact_store import SqlAlchemyControlPlaneArtifactStore
from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .decision_store import SqlAlchemyControlPlaneDecisionStore
from .evolution_proposal_store import SqlAlchemyControlPlaneEvolutionProposalStore
from .goal_store import SqlAlchemyControlPlaneGoalStore
from .models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
    Decision,
    EvolutionProposal,
    Goal,
    WorkItem,
)
from .prompt_config_store import SqlAlchemyControlPlanePromptConfigStore
from .tables import (
    AgentPromptConfigTable,
    AgentRoleTable,
    AgentRunTable,
    ApprovalRequestTable,
    ArtifactTable,
    AuditEventTable,
    BudgetPolicyTable,
    BudgetUsageTable,
    CompanyContextTable,
    DecisionTable,
    EvolutionProposalTable,
    GoalTable,
    WorkItemTable,
)
from .work_item_store import SqlAlchemyControlPlaneWorkItemStore


class ControlPlaneRepository:
    """Data access for the SPEC control-plane objects."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await SqlAlchemyControlPlaneCompanyStore(self.session).create_company(
            company
        )

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await SqlAlchemyControlPlaneCompanyStore(self.session).get_company(
            company_id
        )

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CompanyContextTable]:
        return await SqlAlchemyControlPlaneCompanyStore(
            self.session
        ).list_companies(search=search, limit=limit)

    async def update_company_context(
        self,
        company_id: str,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContextTable | None:
        return await SqlAlchemyControlPlaneCompanyStore(
            self.session
        ).update_company_context(
            company_id,
            name=name,
            mission=mission,
            metadata=metadata,
        )

    async def create_goal(self, goal: Goal) -> GoalTable:
        return await SqlAlchemyControlPlaneGoalStore(self.session).create_goal(goal)

    async def get_goal(self, goal_id: str) -> GoalTable | None:
        return await SqlAlchemyControlPlaneGoalStore(self.session).get_goal(goal_id)

    async def list_goals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[GoalTable]:
        return await SqlAlchemyControlPlaneGoalStore(self.session).list_goals(
            company_id=company_id,
            status=status,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )

    async def update_goal_status(
        self,
        goal_id: str,
        *,
        status: str,
        current_value: float | None = None,
    ) -> GoalTable | None:
        return await SqlAlchemyControlPlaneGoalStore(
            self.session
        ).update_goal_status(
            goal_id,
            status=status,
            current_value=current_value,
        )

    async def create_agent_role(self, role: AgentRole) -> AgentRoleTable:
        return await SqlAlchemyControlPlaneAgentRegistryStore(
            self.session
        ).create_agent_role(role)

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentRoleTable | None:
        return await SqlAlchemyControlPlaneAgentRegistryStore(
            self.session
        ).get_agent_role(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        status: str | None = None,
        agent_kind: str | None = None,
        interaction_mode: str | None = None,
        adapter_type: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[AgentRoleTable]:
        return await SqlAlchemyControlPlaneAgentRegistryStore(
            self.session
        ).list_agent_roles(
            company_id=company_id,
            status=status,
            agent_kind=agent_kind,
            interaction_mode=interaction_mode,
            adapter_type=adapter_type,
            search=search,
            limit=limit,
        )

    async def update_agent_role_status(
        self,
        *,
        company_id: str,
        agent_id: str,
        status: str,
    ) -> AgentRoleTable | None:
        return await SqlAlchemyControlPlaneAgentRegistryStore(
            self.session
        ).update_agent_role_status(
            company_id=company_id,
            agent_id=agent_id,
            status=status,
        )

    async def update_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
        values: dict[str, Any],
    ) -> AgentRoleTable | None:
        return await SqlAlchemyControlPlaneAgentRegistryStore(
            self.session
        ).update_agent_role(
            company_id=company_id,
            agent_id=agent_id,
            values=values,
        )

    async def get_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentPromptConfigTable | None:
        return await SqlAlchemyControlPlanePromptConfigStore(
            self.session
        ).get_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
        )

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPromptConfigTable:
        return await SqlAlchemyControlPlanePromptConfigStore(
            self.session
        ).upsert_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
            system_prompt=system_prompt,
            updated_by=updated_by,
            metadata=metadata,
        )

    async def create_work_item(self, work_item: WorkItem) -> WorkItemTable:
        return await SqlAlchemyControlPlaneWorkItemStore(
            self.session
        ).create_work_item(work_item)

    async def get_work_item(self, work_item_id: str) -> WorkItemTable | None:
        return await SqlAlchemyControlPlaneWorkItemStore(
            self.session
        ).get_work_item(work_item_id)

    async def list_work_items(
        self,
        *,
        company_id: str,
        status: str | None = None,
        priority: str | None = None,
        goal_id: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[WorkItemTable]:
        return await SqlAlchemyControlPlaneWorkItemStore(
            self.session
        ).list_work_items(
            company_id=company_id,
            status=status,
            priority=priority,
            goal_id=goal_id,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )

    async def update_work_item_status(
        self,
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> WorkItemTable | None:
        return await SqlAlchemyControlPlaneWorkItemStore(
            self.session
        ).update_work_item_status(
            work_item_id,
            status=status,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
        )

    async def create_agent_run(self, run: AgentRun) -> AgentRunTable:
        return await SqlAlchemyControlPlaneAgentRunStore(
            self.session
        ).create_agent_run(run)

    async def get_agent_run(self, run_id: str) -> AgentRunTable | None:
        return await SqlAlchemyControlPlaneAgentRunStore(
            self.session
        ).get_agent_run(run_id)

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        status: str | None = None,
        agent_id: str | None = None,
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRunTable]:
        return await SqlAlchemyControlPlaneAgentRunStore(
            self.session
        ).list_agent_runs(
            company_id=company_id,
            status=status,
            agent_id=agent_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )

    async def update_agent_run_status(
        self,
        run_id: str,
        status: AgentRunStatus | str,
        *,
        error_category: str | None = None,
        error_message: str | None = None,
        last_successful_step: str | None = None,
        output_events: list[dict[str, Any]] | None = None,
        cost_usd: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AgentRunTable | None:
        return await SqlAlchemyControlPlaneAgentRunStore(
            self.session
        ).update_agent_run_status(
            run_id,
            status,
            error_category=error_category,
            error_message=error_message,
            last_successful_step=last_successful_step,
            output_events=output_events,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> AgentRunTable | None:
        return await SqlAlchemyControlPlaneAgentRunStore(
            self.session
        ).add_agent_run_usage(
            run_id,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def create_decision(self, decision: Decision) -> DecisionTable:
        return await SqlAlchemyControlPlaneDecisionStore(
            self.session
        ).create_decision(decision)

    async def get_decision(self, decision_id: str) -> DecisionTable | None:
        return await SqlAlchemyControlPlaneDecisionStore(
            self.session
        ).get_decision(decision_id)

    async def list_decisions(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[DecisionTable]:
        return await SqlAlchemyControlPlaneDecisionStore(
            self.session
        ).list_decisions(
            company_id=company_id,
            status=status,
            run_id=run_id,
            run_ids=run_ids,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )

    async def update_decision_status(
        self,
        decision_id: str,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> DecisionTable | None:
        return await SqlAlchemyControlPlaneDecisionStore(
            self.session
        ).update_decision_status(
            decision_id,
            status=status,
            selected_option=selected_option,
            decided_by=decided_by,
        )

    async def request_approval(self, approval: ApprovalRequest) -> ApprovalRequestTable:
        return await SqlAlchemyControlPlaneApprovalStore(
            self.session
        ).request_approval(approval)

    async def get_approval(self, approval_id: str) -> ApprovalRequestTable | None:
        return await SqlAlchemyControlPlaneApprovalStore(
            self.session
        ).get_approval(approval_id)

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequestTable]:
        return await SqlAlchemyControlPlaneApprovalStore(
            self.session
        ).list_approvals(
            company_id=company_id,
            status=status,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequestTable | None:
        return await SqlAlchemyControlPlaneApprovalStore(
            self.session
        ).resolve_approval(
            approval_id,
            status=status,
            resolved_by=resolved_by,
        )

    async def create_artifact(self, artifact: Artifact) -> ArtifactTable:
        return await SqlAlchemyControlPlaneArtifactStore(
            self.session
        ).create_artifact(artifact)

    async def get_artifact(self, artifact_id: str) -> ArtifactTable | None:
        return await SqlAlchemyControlPlaneArtifactStore(
            self.session
        ).get_artifact(artifact_id)

    async def list_artifacts(
        self,
        *,
        company_id: str,
        artifact_type: str | None = None,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = 50,
    ) -> list[ArtifactTable]:
        return await SqlAlchemyControlPlaneArtifactStore(
            self.session
        ).list_artifacts(
            company_id=company_id,
            artifact_type=artifact_type,
            run_id=run_id,
            run_ids=run_ids,
            goal_id=goal_id,
            work_item_id=work_item_id,
            created_by_agent_id=created_by_agent_id,
            limit=limit,
        )

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicyTable:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).create_budget_policy(budget)

    async def get_budget_policy(self, budget_id: str) -> BudgetPolicyTable | None:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).get_budget_policy(budget_id)

    async def list_budget_policies(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str | None = None,
        scope_id: str | None = None,
        period: BudgetPeriod | str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[BudgetPolicyTable]:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).list_budget_policies(
            company_id=company_id,
            scope=scope,
            scope_id=scope_id,
            period=period,
            status=status,
            limit=limit,
        )

    async def update_budget_policy(
        self,
        budget_id: str,
        *,
        limit_usd: float | None = None,
        warning_threshold: float | None = None,
        status: str | None = None,
        model_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetPolicyTable | None:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).update_budget_policy(
            budget_id,
            limit_usd=limit_usd,
            warning_threshold=warning_threshold,
            status=status,
            model_allowlist=model_allowlist,
            metadata=metadata,
        )

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicyTable | None:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).get_active_budget_policy(
            company_id=company_id,
            scope=scope,
            period=period,
            scope_id=scope_id,
        )

    async def record_budget_usage(self, usage: BudgetUsage) -> BudgetUsageTable:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).record_budget_usage(usage)

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsageTable]:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).list_budget_usage(
            company_id=company_id,
            budget_id=budget_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def get_budget_usage_total(self, budget_id: str) -> float:
        return await SqlAlchemyControlPlaneBudgetStore(
            self.session
        ).get_budget_usage_total(budget_id)

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await SqlAlchemyControlPlaneAuditEventStore(
            self.session
        ).append_audit_event(event)

    async def list_audit_events(
        self,
        *,
        company_id: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEventTable]:
        return await SqlAlchemyControlPlaneAuditEventStore(
            self.session
        ).list_audit_events(
            company_id=company_id,
            trace_id=trace_id,
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )

    async def create_evolution_proposal(
        self, proposal: EvolutionProposal
    ) -> EvolutionProposalTable:
        return await SqlAlchemyControlPlaneEvolutionProposalStore(
            self.session
        ).create_evolution_proposal(proposal)

    async def get_evolution_proposal(
        self, proposal_id: str
    ) -> EvolutionProposalTable | None:
        return await SqlAlchemyControlPlaneEvolutionProposalStore(
            self.session
        ).get_evolution_proposal(proposal_id)

    async def list_evolution_proposals(
        self,
        *,
        company_id: str,
        tier: str | None = None,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionProposalTable]:
        return await SqlAlchemyControlPlaneEvolutionProposalStore(
            self.session
        ).list_evolution_proposals(
            company_id=company_id,
            tier=tier,
            approval_state=approval_state,
            rollout_state=rollout_state,
            scope=scope,
            limit=limit,
        )

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> EvolutionProposalTable | None:
        return await SqlAlchemyControlPlaneEvolutionProposalStore(
            self.session
        ).update_evolution_proposal_status(
            proposal_id,
            approval_state=approval_state,
            rollout_state=rollout_state,
            approval_id=approval_id,
        )

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: str,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ) -> EvolutionProposalTable | None:
        return await SqlAlchemyControlPlaneEvolutionProposalStore(
            self.session
        ).update_evolution_proposal_approval_state_by_approval(
            approval_id,
            approval_state=approval_state,
            rollout_state=rollout_state,
        )
