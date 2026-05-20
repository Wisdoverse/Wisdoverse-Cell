"""Domain-record mappers for control-plane application use cases."""
from __future__ import annotations

from .models import (
    AgentRole,
    AgentRun,
    ApprovalRequest,
    AuditEvent,
    BudgetPolicy,
    BudgetUsage,
    CompanyContext,
    Decision,
    EvolutionProposal,
    Goal,
    WorkItem,
)
from .models import Artifact as ArtifactModel
from .tables import (
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


def company_record(row: CompanyContextTable) -> CompanyContext:
    """Convert a company ORM row into its domain model."""
    return CompanyContext(
        company_id=row.company_id,
        name=row.name,
        mission=row.mission,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def goal_record(row: GoalTable) -> Goal:
    """Convert a goal ORM row into its domain model."""
    return Goal(
        goal_id=row.goal_id,
        company_id=row.company_id,
        title=row.title,
        description=row.description,
        status=row.status,
        parent_goal_id=row.parent_goal_id,
        owner_agent_id=row.owner_agent_id,
        owner_user_id=row.owner_user_id,
        success_metric=row.success_metric,
        target_value=row.target_value,
        current_value=row.current_value,
        due_at=row.due_at,
        tags=list(row.tags or []),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def agent_role_record(row: AgentRoleTable) -> AgentRole:
    """Convert an agent-role ORM row into its domain model."""
    return AgentRole(
        role_id=row.role_id,
        company_id=row.company_id,
        agent_id=row.agent_id,
        display_name=row.display_name,
        agent_kind=row.agent_kind,
        interaction_mode=row.interaction_mode,
        role=row.role,
        title=row.title,
        domain=row.domain,
        reports_to_agent_id=row.reports_to_agent_id,
        adapter_type=row.adapter_type,
        adapter_config=dict(row.adapter_config or {}),
        context_sources=list(row.context_sources or []),
        capabilities=list(row.capabilities or []),
        responsibilities=list(row.responsibilities or []),
        subscribed_events=list(row.subscribed_events or []),
        published_events=list(row.published_events or []),
        permissions=list(row.permissions or []),
        budget_policy_id=row.budget_policy_id,
        escalation_policy=dict(row.escalation_policy or {}),
        status=row.status,
        created_by=row.created_by,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def work_item_record(row: WorkItemTable) -> WorkItem:
    """Convert a work-item ORM row into its domain model."""
    return WorkItem(
        work_item_id=row.work_item_id,
        company_id=row.company_id,
        title=row.title,
        description=row.description,
        status=row.status,
        priority=row.priority,
        goal_id=row.goal_id,
        owner_agent_id=row.owner_agent_id,
        owner_user_id=row.owner_user_id,
        source=row.source,
        external_ref=row.external_ref,
        dependencies=list(row.dependencies or []),
        approval_required=row.approval_required,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def agent_run_record(row: AgentRunTable) -> AgentRun:
    """Convert an agent-run ORM row into its domain model."""
    return AgentRun(
        run_id=row.run_id,
        company_id=row.company_id,
        agent_id=row.agent_id,
        status=row.status,
        trace_id=row.trace_id,
        goal_id=row.goal_id,
        work_item_id=row.work_item_id,
        trigger_event_id=row.trigger_event_id,
        input_event=dict(row.input_event or {}) if row.input_event is not None else None,
        output_events=list(row.output_events or []),
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_category=row.error_category,
        error_message=row.error_message,
        last_successful_step=row.last_successful_step,
        cost_usd=row.cost_usd,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        metadata=dict(row.metadata_json or {}),
    )


def decision_record(row: DecisionTable) -> Decision:
    """Convert a decision ORM row into its domain model."""
    return Decision(
        decision_id=row.decision_id,
        company_id=row.company_id,
        title=row.title,
        rationale=row.rationale,
        status=row.status,
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        goal_id=row.goal_id,
        options=list(row.options or []),
        selected_option=row.selected_option,
        decided_by=row.decided_by,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def approval_request_record(row: ApprovalRequestTable) -> ApprovalRequest:
    """Convert an approval-request ORM row into its domain model."""
    return ApprovalRequest(
        approval_id=row.approval_id,
        company_id=row.company_id,
        category=row.category,
        status=row.status,
        requested_by=row.requested_by,
        source_agent_id=row.source_agent_id,
        proposed_action=row.proposed_action,
        reason=row.reason,
        risk=row.risk,
        rollback_note=row.rollback_note,
        affected_resources=list(row.affected_resources or []),
        artifact_links=list(row.artifact_links or []),
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        goal_id=row.goal_id,
        trace_id=row.trace_id,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        expires_at=row.expires_at,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def artifact_record(row: ArtifactTable) -> ArtifactModel:
    """Convert an artifact ORM row into its domain model."""
    return ArtifactModel(
        artifact_id=row.artifact_id,
        company_id=row.company_id,
        artifact_type=row.artifact_type,
        title=row.title,
        uri=row.uri,
        content_hash=row.content_hash,
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        goal_id=row.goal_id,
        created_by_agent_id=row.created_by_agent_id,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
    )


def budget_policy_record(row: BudgetPolicyTable) -> BudgetPolicy:
    """Convert a budget-policy ORM row into its domain model."""
    return BudgetPolicy(
        budget_id=row.budget_id,
        company_id=row.company_id,
        scope=row.scope,
        period=row.period,
        limit_usd=row.limit_usd,
        scope_id=row.scope_id,
        warning_threshold=row.warning_threshold,
        status=row.status,
        model_allowlist=list(row.model_allowlist or []),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def budget_usage_record(row: BudgetUsageTable) -> BudgetUsage:
    """Convert a budget-usage ORM row into its domain model."""
    return BudgetUsage(
        usage_id=row.usage_id,
        company_id=row.company_id,
        budget_id=row.budget_id,
        cost_usd=row.cost_usd,
        model=row.model,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        run_id=row.run_id,
        trace_id=row.trace_id,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
    )


def audit_event_record(row: AuditEventTable) -> AuditEvent:
    """Convert an audit-event ORM row into its domain model."""
    return AuditEvent(
        audit_event_id=row.audit_event_id,
        company_id=row.company_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        trace_id=row.trace_id,
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        idempotency_key=row.idempotency_key,
        detail=dict(row.detail or {}),
        created_at=row.created_at,
    )


def evolution_proposal_record(row: EvolutionProposalTable) -> EvolutionProposal:
    """Convert an evolution-proposal ORM row into its domain model."""
    return EvolutionProposal(
        proposal_id=row.proposal_id,
        company_id=row.company_id,
        tier=row.tier,
        scope=row.scope,
        evidence=dict(row.evidence or {}),
        expected_benefit=row.expected_benefit,
        risk=row.risk,
        approval_state=row.approval_state,
        rollout_state=row.rollout_state,
        approval_id=row.approval_id,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
