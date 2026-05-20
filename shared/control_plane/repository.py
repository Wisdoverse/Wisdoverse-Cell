"""Repository layer for the shared control-plane ledger."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .approval_store import SqlAlchemyControlPlaneApprovalStore
from .artifact_store import SqlAlchemyControlPlaneArtifactStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .decision_store import SqlAlchemyControlPlaneDecisionStore
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


def _now() -> datetime:
    return datetime.now(UTC)


def _to_db_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_to_db_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_db_value(item) for key, item in value.items()}
    return value


def _model_values(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump(mode="python")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        db_key = "metadata_json" if key == "metadata" else key
        normalized[db_key] = _to_db_value(value)
    return normalized


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
        row = AgentRoleTable(**_model_values(role))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentRoleTable | None:
        result = await self.session.execute(
            select(AgentRoleTable).where(
                AgentRoleTable.company_id == company_id,
                AgentRoleTable.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

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
        query = select(AgentRoleTable).where(AgentRoleTable.company_id == company_id)
        if status:
            query = query.where(AgentRoleTable.status == status)
        if agent_kind:
            query = query.where(AgentRoleTable.agent_kind == agent_kind)
        if interaction_mode:
            query = query.where(AgentRoleTable.interaction_mode == interaction_mode)
        if adapter_type:
            query = query.where(AgentRoleTable.adapter_type == adapter_type)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    AgentRoleTable.agent_id.ilike(pattern),
                    AgentRoleTable.display_name.ilike(pattern),
                    AgentRoleTable.role.ilike(pattern),
                    AgentRoleTable.title.ilike(pattern),
                )
            )
        result = await self.session.execute(
            query.order_by(AgentRoleTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_agent_role_status(
        self,
        *,
        company_id: str,
        agent_id: str,
        status: str,
    ) -> AgentRoleTable | None:
        row = await self.get_agent_role(company_id=company_id, agent_id=agent_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def update_agent_role(
        self,
        *,
        company_id: str,
        agent_id: str,
        values: dict[str, Any],
    ) -> AgentRoleTable | None:
        row = await self.get_agent_role(company_id=company_id, agent_id=agent_id)
        if row is None:
            return None

        for key, value in values.items():
            db_key = "metadata_json" if key == "metadata" else key
            setattr(row, db_key, _to_db_value(value))
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def get_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
    ) -> AgentPromptConfigTable | None:
        result = await self.session.execute(
            select(AgentPromptConfigTable).where(
                AgentPromptConfigTable.company_id == company_id,
                AgentPromptConfigTable.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_agent_prompt_config(
        self,
        *,
        company_id: str,
        agent_id: str,
        system_prompt: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPromptConfigTable:
        row = await self.get_agent_prompt_config(
            company_id=company_id,
            agent_id=agent_id,
        )
        if row is None:
            row = AgentPromptConfigTable(
                company_id=company_id,
                agent_id=agent_id,
                system_prompt=system_prompt,
                updated_by=updated_by,
                metadata_json=_to_db_value(metadata or {}),
            )
            self.session.add(row)
        else:
            row.system_prompt = system_prompt
            row.updated_by = updated_by
            if metadata is not None:
                row.metadata_json = _to_db_value(metadata)
            row.updated_at = _now()
        await self.session.flush()
        return row

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
        if event.idempotency_key:
            existing = await self._get_audit_by_idempotency(
                event.company_id, event.idempotency_key
            )
            if existing is not None:
                return existing

        row = AuditEventTable(**_model_values(event))
        self.session.add(row)
        await self.session.flush()
        return row

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
        query = select(AuditEventTable).where(AuditEventTable.company_id == company_id)
        if trace_id:
            query = query.where(AuditEventTable.trace_id == trace_id)
        if run_id:
            query = query.where(AuditEventTable.run_id == run_id)
        if target_type:
            query = query.where(AuditEventTable.target_type == target_type)
        if target_id:
            query = query.where(AuditEventTable.target_id == target_id)
        result = await self.session.execute(
            query.order_by(AuditEventTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def _get_audit_by_idempotency(
        self, company_id: str, idempotency_key: str
    ) -> AuditEventTable | None:
        result = await self.session.execute(
            select(AuditEventTable).where(
                AuditEventTable.company_id == company_id,
                AuditEventTable.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def create_evolution_proposal(
        self, proposal: EvolutionProposal
    ) -> EvolutionProposalTable:
        row = EvolutionProposalTable(**_model_values(proposal))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_evolution_proposal(
        self, proposal_id: str
    ) -> EvolutionProposalTable | None:
        result = await self.session.execute(
            select(EvolutionProposalTable).where(
                EvolutionProposalTable.proposal_id == proposal_id
            )
        )
        return result.scalar_one_or_none()

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
        query = select(EvolutionProposalTable).where(
            EvolutionProposalTable.company_id == company_id
        )
        if tier:
            query = query.where(EvolutionProposalTable.tier == tier)
        if approval_state:
            query = query.where(
                EvolutionProposalTable.approval_state == approval_state
            )
        if rollout_state:
            query = query.where(EvolutionProposalTable.rollout_state == rollout_state)
        if scope:
            query = query.where(EvolutionProposalTable.scope.ilike(f"%{scope}%"))
        result = await self.session.execute(
            query.order_by(EvolutionProposalTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_evolution_proposal_status(
        self,
        proposal_id: str,
        *,
        approval_state: str | None = None,
        rollout_state: str | None = None,
        approval_id: str | None = None,
    ) -> EvolutionProposalTable | None:
        row = await self.get_evolution_proposal(proposal_id)
        if row is None:
            return None
        if approval_state is not None:
            row.approval_state = approval_state
        if rollout_state is not None:
            row.rollout_state = rollout_state
        if approval_id is not None:
            row.approval_id = approval_id
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def update_evolution_proposal_approval_state_by_approval(
        self,
        approval_id: str,
        *,
        approval_state: str,
        rollout_state: str | None = None,
    ) -> EvolutionProposalTable | None:
        return await SqlAlchemyControlPlaneApprovalStore(
            self.session
        ).update_evolution_proposal_approval_state_by_approval(
            approval_id,
            approval_state=approval_state,
            rollout_state=rollout_state,
        )
