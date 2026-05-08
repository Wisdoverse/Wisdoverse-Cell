"""SQLAlchemy tables for the SPEC control-plane ledger."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def _now() -> datetime:
    return datetime.now(UTC)


control_plane_metadata = MetaData()


class ControlPlaneBase(DeclarativeBase):
    metadata = control_plane_metadata


class CompanyContextTable(ControlPlaneBase):
    __tablename__ = "control_plane_companies"

    company_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class GoalTable(ControlPlaneBase):
    __tablename__ = "control_plane_goals"

    goal_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="draft")
    parent_goal_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True
    )
    owner_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    success_metric: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_control_goals_company_status_created", "company_id", "status", "created_at"),
    )


class AgentRoleTable(ControlPlaneBase):
    __tablename__ = "control_plane_agent_roles"

    role_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="organization_role", index=True
    )
    interaction_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="routed", index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="worker", index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    reports_to_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False, default="builtin", index=True)
    adapter_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    context_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    responsibilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    subscribed_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    published_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    budget_policy_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    escalation_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("company_id", "agent_id", name="uq_control_agent_role_company_agent"),
    )


class AgentPromptConfigTable(ControlPlaneBase):
    __tablename__ = "control_plane_agent_prompt_configs"

    company_id: Mapped[str] = mapped_column(
        String(48),
        ForeignKey("control_plane_companies.company_id"),
        primary_key=True,
    )
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_control_prompt_configs_agent", "agent_id"),
    )


class WorkItemTable(ControlPlaneBase):
    __tablename__ = "control_plane_work_items"

    work_item_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="queued")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    goal_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True, index=True
    )
    owner_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("company_id", "external_ref", name="uq_control_work_company_external_ref"),
        Index("ix_control_work_company_status_created", "company_id", "status", "created_at"),
    )


class AgentRunTable(ControlPlaneBase):
    __tablename__ = "control_plane_agent_runs"

    run_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    goal_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True)
    work_item_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), nullable=True, index=True
    )
    trigger_event_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    input_event: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_control_runs_company_status_started", "company_id", "status", "started_at"),
        Index("ix_control_runs_agent_started", "agent_id", "started_at"),
    )


class DecisionTable(ControlPlaneBase):
    __tablename__ = "control_plane_decisions"

    decision_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True)
    run_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_agent_runs.run_id"), nullable=True, index=True
    )
    work_item_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), nullable=True
    )
    goal_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True)
    options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    selected_option: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class ApprovalRequestTable(ControlPlaneBase):
    __tablename__ = "control_plane_approval_requests"

    approval_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    source_agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    proposed_action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_note: Mapped[str] = mapped_column(Text, nullable=False)
    affected_resources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    artifact_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    run_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_agent_runs.run_id"), nullable=True)
    work_item_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), nullable=True
    )
    goal_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_control_approvals_company_status_created", "company_id", "status", "created_at"),
    )


class ArtifactTable(ControlPlaneBase):
    __tablename__ = "control_plane_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_agent_runs.run_id"), nullable=True)
    work_item_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), nullable=True
    )
    goal_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_goals.goal_id"), nullable=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)


class BudgetPolicyTable(ControlPlaneBase):
    __tablename__ = "control_plane_budget_policies"

    budget_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_usd: Mapped[float] = mapped_column(Float, nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    model_allowlist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_control_budget_company_scope", "company_id", "scope", "scope_id"),
    )


class BudgetUsageTable(ControlPlaneBase):
    __tablename__ = "control_plane_budget_usage"

    usage_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    budget_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_budget_policies.budget_id"), nullable=False, index=True
    )
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_agent_runs.run_id"), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    __table_args__ = (
        Index("ix_control_budget_usage_budget_created", "budget_id", "created_at"),
    )


class AuditEventTable(ControlPlaneBase):
    __tablename__ = "control_plane_audit_events"

    audit_event_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("control_plane_agent_runs.run_id"), nullable=True)
    work_item_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    __table_args__ = (
        UniqueConstraint("company_id", "idempotency_key", name="uq_control_audit_idempotency"),
        Index("ix_control_audit_company_created", "company_id", "created_at"),
        Index("ix_control_audit_target", "target_type", "target_id"),
    )


class EvolutionProposalTable(ControlPlaneBase):
    __tablename__ = "control_plane_evolution_proposals"

    proposal_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    approval_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    rollout_state: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True)
    approval_id: Mapped[str | None] = mapped_column(
        String(48), ForeignKey("control_plane_approval_requests.approval_id"), nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
