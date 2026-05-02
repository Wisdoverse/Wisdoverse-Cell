"""Pydantic models for the SPEC control-plane domain.

These models are the shared contract for durable company operations data:
goals, work items, agent runs, approvals, budgets, artifacts, and audit events.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.utils.id_generator import IDPrefix, generate_id


def _now() -> datetime:
    return datetime.now(UTC)


class GoalStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkItemStatus(StrEnum):
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItemPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentKind(StrEnum):
    ORGANIZATION_ROLE = "organization_role"
    CAPABILITY_MODULE = "capability_module"
    INTEGRATION_GATEWAY = "integration_gateway"
    SYSTEM_WORKER = "system_worker"


class AgentInteractionMode(StrEnum):
    DIRECT = "direct"
    ROUTED = "routed"
    INTERNAL = "internal"
    NONE = "none"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ApprovalCategory(StrEnum):
    FINANCE = "finance"
    LEGAL = "legal"
    CUSTOMER = "customer"
    TECHNICAL = "technical"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ArtifactType(StrEnum):
    PRD = "prd"
    REPORT = "report"
    QA_RESULT = "qa_result"
    ISSUE = "issue"
    MERGE_REQUEST = "merge_request"
    CODE_PATCH = "code_patch"
    RUN_WALKTHROUGH = "run_walkthrough"
    OTHER = "other"


class BudgetScope(StrEnum):
    COMPANY = "company"
    GOAL = "goal"
    AGENT = "agent"
    WORK_ITEM = "work_item"


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    TOTAL = "total"


class EvolutionTier(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class EvolutionRolloutState(StrEnum):
    PROPOSED = "proposed"
    SHADOW = "shadow"
    CANARY = "canary"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class ControlPlaneModel(BaseModel):
    """Base Pydantic config for control-plane models."""

    model_config = ConfigDict(
        use_enum_values=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CompanyContext(ControlPlaneModel):
    company_id: str = Field(default_factory=lambda: generate_id(IDPrefix.COMPANY))
    name: str
    mission: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Goal(ControlPlaneModel):
    goal_id: str = Field(default_factory=lambda: generate_id(IDPrefix.GOAL))
    company_id: str
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.DRAFT
    parent_goal_id: str | None = None
    owner_agent_id: str | None = None
    owner_user_id: str | None = None
    success_metric: str = ""
    target_value: float | None = None
    current_value: float | None = None
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class AgentRole(ControlPlaneModel):
    role_id: str = Field(default_factory=lambda: generate_id(IDPrefix.AGENT_ROLE))
    company_id: str
    agent_id: str
    display_name: str
    agent_kind: AgentKind = AgentKind.ORGANIZATION_ROLE
    interaction_mode: AgentInteractionMode = AgentInteractionMode.ROUTED
    role: str = "worker"
    title: str = ""
    domain: str = ""
    reports_to_agent_id: str | None = None
    adapter_type: str = "builtin"
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    context_sources: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    budget_policy_id: str | None = None
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    created_by: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class WorkItem(ControlPlaneModel):
    work_item_id: str = Field(default_factory=lambda: generate_id(IDPrefix.WORK_ITEM))
    company_id: str
    title: str
    description: str = ""
    status: WorkItemStatus = WorkItemStatus.QUEUED
    priority: WorkItemPriority = WorkItemPriority.MEDIUM
    goal_id: str | None = None
    owner_agent_id: str | None = None
    owner_user_id: str | None = None
    source: str = "manual"
    external_ref: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    approval_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class AgentRun(ControlPlaneModel):
    run_id: str = Field(default_factory=lambda: generate_id(IDPrefix.AGENT_RUN))
    company_id: str
    agent_id: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    trace_id: str | None = None
    goal_id: str | None = None
    work_item_id: str | None = None
    trigger_event_id: str | None = None
    input_event: dict[str, Any] | None = None
    output_events: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None
    error_category: str | None = None
    error_message: str | None = None
    last_successful_step: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Decision(ControlPlaneModel):
    decision_id: str = Field(default_factory=lambda: generate_id(IDPrefix.DECISION))
    company_id: str
    title: str
    rationale: str
    status: DecisionStatus = DecisionStatus.PROPOSED
    run_id: str | None = None
    work_item_id: str | None = None
    goal_id: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    selected_option: str | None = None
    decided_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ApprovalRequest(ControlPlaneModel):
    approval_id: str = Field(default_factory=lambda: generate_id(IDPrefix.APPROVAL))
    company_id: str
    category: ApprovalCategory
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: str
    source_agent_id: str
    proposed_action: str
    reason: str
    risk: str
    rollback_note: str
    affected_resources: list[str] = Field(default_factory=list)
    artifact_links: list[str] = Field(default_factory=list)
    run_id: str | None = None
    work_item_id: str | None = None
    goal_id: str | None = None
    trace_id: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("proposed_action", "reason", "risk", "rollback_note")
    @classmethod
    def _must_include_decision_context(cls, value: str) -> str:
        if not value:
            raise ValueError("approval requests require action, reason, risk, and rollback context")
        return value


class Artifact(ControlPlaneModel):
    artifact_id: str = Field(default_factory=lambda: generate_id(IDPrefix.ARTIFACT))
    company_id: str
    artifact_type: ArtifactType = ArtifactType.OTHER
    title: str
    uri: str
    content_hash: str | None = None
    run_id: str | None = None
    work_item_id: str | None = None
    goal_id: str | None = None
    created_by_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class BudgetPolicy(ControlPlaneModel):
    budget_id: str = Field(default_factory=lambda: generate_id(IDPrefix.BUDGET))
    company_id: str
    scope: BudgetScope
    period: BudgetPeriod
    limit_usd: float
    scope_id: str | None = None
    warning_threshold: float = 0.8
    status: str = "active"
    model_allowlist: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("limit_usd")
    @classmethod
    def _limit_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("budget limit must be positive")
        return value


class BudgetUsage(ControlPlaneModel):
    usage_id: str = Field(default_factory=lambda: generate_id(IDPrefix.BUDGET_USAGE))
    company_id: str
    budget_id: str
    cost_usd: float
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    run_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class AuditEvent(ControlPlaneModel):
    audit_event_id: str = Field(default_factory=lambda: generate_id(IDPrefix.AUDIT_EVENT))
    company_id: str
    action: str
    target_type: str
    target_id: str
    actor_type: str = "system"
    actor_id: str = ""
    trace_id: str | None = None
    run_id: str | None = None
    work_item_id: str | None = None
    idempotency_key: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class EvolutionProposal(ControlPlaneModel):
    proposal_id: str = Field(default_factory=lambda: generate_id(IDPrefix.EVOLUTION_PROPOSAL))
    company_id: str
    tier: EvolutionTier
    scope: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    expected_benefit: str
    risk: str
    approval_state: ApprovalStatus = ApprovalStatus.PENDING
    rollout_state: EvolutionRolloutState = EvolutionRolloutState.PROPOSED
    approval_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
