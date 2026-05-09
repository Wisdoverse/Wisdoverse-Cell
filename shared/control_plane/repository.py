"""Repository layer for the shared control-plane ledger."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        row = CompanyContextTable(**_model_values(company))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        result = await self.session.execute(
            select(CompanyContextTable).where(CompanyContextTable.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CompanyContextTable]:
        query = select(CompanyContextTable)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    CompanyContextTable.company_id.ilike(pattern),
                    CompanyContextTable.name.ilike(pattern),
                    CompanyContextTable.mission.ilike(pattern),
                )
            )
        result = await self.session.execute(
            query.order_by(CompanyContextTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_company_context(
        self,
        company_id: str,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContextTable | None:
        row = await self.get_company(company_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if mission is not None:
            row.mission = mission
        if metadata is not None:
            row.metadata_json = _to_db_value(metadata)
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def create_goal(self, goal: Goal) -> GoalTable:
        row = GoalTable(**_model_values(goal))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_goal(self, goal_id: str) -> GoalTable | None:
        result = await self.session.execute(select(GoalTable).where(GoalTable.goal_id == goal_id))
        return result.scalar_one_or_none()

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
        query = select(GoalTable).where(GoalTable.company_id == company_id)
        if status:
            query = query.where(GoalTable.status == status)
        if owner_agent_id:
            query = query.where(GoalTable.owner_agent_id == owner_agent_id)
        if owner_user_id:
            query = query.where(GoalTable.owner_user_id == owner_user_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    GoalTable.title.ilike(pattern),
                    GoalTable.description.ilike(pattern),
                    GoalTable.success_metric.ilike(pattern),
                )
            )
        result = await self.session.execute(
            query.order_by(GoalTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_goal_status(
        self,
        goal_id: str,
        *,
        status: str,
        current_value: float | None = None,
    ) -> GoalTable | None:
        row = await self.get_goal(goal_id)
        if row is None:
            return None
        row.status = status
        if current_value is not None:
            row.current_value = current_value
        row.updated_at = _now()
        await self.session.flush()
        return row

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
        row = WorkItemTable(**_model_values(work_item))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_work_item(self, work_item_id: str) -> WorkItemTable | None:
        result = await self.session.execute(
            select(WorkItemTable).where(WorkItemTable.work_item_id == work_item_id)
        )
        return result.scalar_one_or_none()

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
        query = select(WorkItemTable).where(WorkItemTable.company_id == company_id)
        if status:
            query = query.where(WorkItemTable.status == status)
        if priority:
            query = query.where(WorkItemTable.priority == priority)
        if goal_id:
            query = query.where(WorkItemTable.goal_id == goal_id)
        if owner_agent_id:
            query = query.where(WorkItemTable.owner_agent_id == owner_agent_id)
        if owner_user_id:
            query = query.where(WorkItemTable.owner_user_id == owner_user_id)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    WorkItemTable.title.ilike(pattern),
                    WorkItemTable.description.ilike(pattern),
                    WorkItemTable.external_ref.ilike(pattern),
                )
            )
        result = await self.session.execute(
            query.order_by(WorkItemTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_work_item_status(
        self,
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> WorkItemTable | None:
        row = await self.get_work_item(work_item_id)
        if row is None:
            return None
        row.status = status
        if owner_agent_id is not None:
            row.owner_agent_id = owner_agent_id
        if owner_user_id is not None:
            row.owner_user_id = owner_user_id
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def create_agent_run(self, run: AgentRun) -> AgentRunTable:
        row = AgentRunTable(**_model_values(run))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_agent_run(self, run_id: str) -> AgentRunTable | None:
        result = await self.session.execute(
            select(AgentRunTable).where(AgentRunTable.run_id == run_id)
        )
        return result.scalar_one_or_none()

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
        query = select(AgentRunTable).where(AgentRunTable.company_id == company_id)
        if status:
            query = query.where(AgentRunTable.status == status)
        if agent_id:
            query = query.where(AgentRunTable.agent_id == agent_id)
        if trace_id:
            query = query.where(AgentRunTable.trace_id == trace_id)
        if goal_id:
            query = query.where(AgentRunTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(AgentRunTable.work_item_id == work_item_id)
        result = await self.session.execute(
            query.order_by(AgentRunTable.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

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
        row = await self.get_agent_run(run_id)
        if row is None:
            return None
        status_value = status.value if isinstance(status, Enum) else status
        row.status = status_value
        if status_value in {
            AgentRunStatus.SUCCEEDED.value,
            AgentRunStatus.FAILED.value,
            AgentRunStatus.CANCELLED.value,
            AgentRunStatus.TIMED_OUT.value,
        }:
            row.completed_at = _now()
        if error_category is not None:
            row.error_category = error_category
        if error_message is not None:
            row.error_message = error_message
        if last_successful_step is not None:
            row.last_successful_step = last_successful_step
        if output_events is not None:
            row.output_events = output_events
        if cost_usd is not None:
            row.cost_usd = cost_usd
        if input_tokens is not None:
            row.input_tokens = input_tokens
        if output_tokens is not None:
            row.output_tokens = output_tokens
        await self.session.flush()
        return row

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> AgentRunTable | None:
        row = await self.get_agent_run(run_id)
        if row is None:
            return None
        row.cost_usd = float(row.cost_usd or 0.0) + cost_usd
        row.input_tokens = int(row.input_tokens or 0) + input_tokens
        row.output_tokens = int(row.output_tokens or 0) + output_tokens
        await self.session.flush()
        return row

    async def create_decision(self, decision: Decision) -> DecisionTable:
        row = DecisionTable(**_model_values(decision))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_decision(self, decision_id: str) -> DecisionTable | None:
        result = await self.session.execute(
            select(DecisionTable).where(DecisionTable.decision_id == decision_id)
        )
        return result.scalar_one_or_none()

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
        query = select(DecisionTable).where(DecisionTable.company_id == company_id)
        if status:
            query = query.where(DecisionTable.status == status)
        if run_id:
            query = query.where(DecisionTable.run_id == run_id)
        elif run_ids:
            query = query.where(DecisionTable.run_id.in_(run_ids))
        if goal_id:
            query = query.where(DecisionTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(DecisionTable.work_item_id == work_item_id)
        result = await self.session.execute(
            query.order_by(DecisionTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_decision_status(
        self,
        decision_id: str,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> DecisionTable | None:
        row = await self.get_decision(decision_id)
        if row is None:
            return None
        row.status = status
        if selected_option is not None:
            row.selected_option = selected_option
        if decided_by is not None:
            row.decided_by = decided_by
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def request_approval(self, approval: ApprovalRequest) -> ApprovalRequestTable:
        row = ApprovalRequestTable(**_model_values(approval))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_approval(self, approval_id: str) -> ApprovalRequestTable | None:
        result = await self.session.execute(
            select(ApprovalRequestTable).where(ApprovalRequestTable.approval_id == approval_id)
        )
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalRequestTable]:
        query = select(ApprovalRequestTable).where(
            ApprovalRequestTable.company_id == company_id
        )
        if status:
            query = query.where(ApprovalRequestTable.status == status)
        if run_id:
            query = query.where(ApprovalRequestTable.run_id == run_id)
        if trace_id:
            query = query.where(ApprovalRequestTable.trace_id == trace_id)
        result = await self.session.execute(
            query.order_by(ApprovalRequestTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus | str,
        resolved_by: str,
    ) -> ApprovalRequestTable | None:
        row = await self.get_approval(approval_id)
        if row is None:
            return None
        status_value = status.value if isinstance(status, Enum) else status
        row.status = status_value
        row.resolved_by = resolved_by
        row.resolved_at = _now()
        row.updated_at = _now()
        await self.session.flush()
        return row

    async def create_artifact(self, artifact: Artifact) -> ArtifactTable:
        row = ArtifactTable(**_model_values(artifact))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_artifact(self, artifact_id: str) -> ArtifactTable | None:
        result = await self.session.execute(
            select(ArtifactTable).where(ArtifactTable.artifact_id == artifact_id)
        )
        return result.scalar_one_or_none()

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
        query = select(ArtifactTable).where(ArtifactTable.company_id == company_id)
        if artifact_type:
            query = query.where(ArtifactTable.artifact_type == artifact_type)
        if run_id:
            query = query.where(ArtifactTable.run_id == run_id)
        elif run_ids:
            query = query.where(ArtifactTable.run_id.in_(run_ids))
        if goal_id:
            query = query.where(ArtifactTable.goal_id == goal_id)
        if work_item_id:
            query = query.where(ArtifactTable.work_item_id == work_item_id)
        if created_by_agent_id:
            query = query.where(ArtifactTable.created_by_agent_id == created_by_agent_id)
        result = await self.session.execute(
            query.order_by(ArtifactTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicyTable:
        row = BudgetPolicyTable(**_model_values(budget))
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicyTable | None:
        scope_value = scope.value if isinstance(scope, Enum) else scope
        period_value = period.value if isinstance(period, Enum) else period
        query = select(BudgetPolicyTable).where(
            BudgetPolicyTable.company_id == company_id,
            BudgetPolicyTable.scope == scope_value,
            BudgetPolicyTable.period == period_value,
            BudgetPolicyTable.status == "active",
        )
        if scope_id is None:
            query = query.where(BudgetPolicyTable.scope_id.is_(None))
        else:
            query = query.where(BudgetPolicyTable.scope_id == scope_id)

        result = await self.session.execute(
            query.order_by(BudgetPolicyTable.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def record_budget_usage(self, usage: BudgetUsage) -> BudgetUsageTable:
        row = BudgetUsageTable(**_model_values(usage))
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsageTable]:
        query = select(BudgetUsageTable).where(BudgetUsageTable.company_id == company_id)
        if budget_id:
            query = query.where(BudgetUsageTable.budget_id == budget_id)
        if run_id:
            query = query.where(BudgetUsageTable.run_id == run_id)
        if trace_id:
            query = query.where(BudgetUsageTable.trace_id == trace_id)
        result = await self.session.execute(
            query.order_by(BudgetUsageTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_budget_usage_total(self, budget_id: str) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(BudgetUsageTable.cost_usd), 0.0)).where(
                BudgetUsageTable.budget_id == budget_id
            )
        )
        return float(result.scalar_one() or 0.0)

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
        result = await self.session.execute(
            select(EvolutionProposalTable).where(
                EvolutionProposalTable.approval_id == approval_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.approval_state = approval_state
        if rollout_state is not None:
            row.rollout_state = rollout_state
        row.updated_at = _now()
        await self.session.flush()
        return row
