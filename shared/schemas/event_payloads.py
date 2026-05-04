"""
Event Payloads - payload contract definitions.

Defines payload formats for event contract tests and type checking. Agents can
use these models as the reference when subscribing to events.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coordinator import (
    AgentProgress,
    CoordinatorCommand,
    CoordinatorResponse,
    TaskNotification,
)

# ============ Requirement Events ============

class RequirementSummary(BaseModel):
    """Requirement summary used in lists."""
    id: str
    title: str
    priority: str
    category: str


class RequirementExtractedPayload(BaseModel):
    """
    requirement.extracted event payload.

    Published when requirements are extracted from a meeting.
    """
    model_config = ConfigDict(strict=True)

    meeting_id: str = Field(..., description="Source meeting ID")
    requirement_ids: list[str] = Field(..., description="Extracted requirement ID list")
    count: int = Field(..., ge=1, description="Number of extracted requirements")
    requirements: list[RequirementSummary] = Field(..., description="Requirement summaries")


class RequirementConfirmedPayload(BaseModel):
    """
    requirement.confirmed event payload.

    Published when a human confirms a requirement.
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="Requirement ID")
    title: str = Field(..., description="Requirement title")
    priority: str = Field(..., description="Priority")
    category: str = Field(..., description="Category")
    confirmed_by: str = Field(..., description="Confirmation actor")
    confirmed_at: str = Field(..., description="Confirmation time (ISO format)")


class RequirementRejectedPayload(BaseModel):
    """
    requirement.rejected event payload.

    Published when a requirement is rejected.
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="Requirement ID")
    title: str = Field(..., description="Requirement title")
    reason: str = Field(..., description="Rejection reason")
    rejected_at: str = Field(..., description="Rejection time (ISO format)")


class RequirementChangedPayload(BaseModel):
    """
    requirement.changed event payload.

    Published when requirement content changes.
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="Requirement ID")
    title: str = Field(..., description="Requirement title")
    changed_fields: list[str] = Field(..., description="Changed field list")
    changed_by: str = Field(..., description="Change actor")
    changed_at: str = Field(..., description="Change time (ISO format)")


class RequirementDeletedPayload(BaseModel):
    """
    requirement.deleted event payload.

    Published when a requirement is deleted.
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="Requirement ID")
    title: str = Field(..., description="Requirement title")
    deleted_by: str = Field(..., description="Deletion actor")
    deleted_at: str = Field(..., description="Deletion time (ISO format)")


# ============ External work context events ============

class ProjectEventPayload(BaseModel):
    """project.created / project.updated event payload."""

    model_config = ConfigDict(strict=True)

    project_id: str | int
    name: str = ""
    keywords: list[str] = Field(default_factory=list)
    changes: dict = Field(default_factory=dict)
    source_system: str = "external"
    source_id: str | None = None


class SprintStartedPayload(BaseModel):
    """sprint.started event payload."""

    model_config = ConfigDict(strict=True)

    sprint_id: str | int
    name: str = ""
    requirement_ids: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None


class SprintCompletedPayload(BaseModel):
    """sprint.completed event payload."""

    model_config = ConfigDict(strict=True)

    sprint_id: str | int
    completed_requirement_ids: list[str] = Field(default_factory=list)
    incomplete_requirement_ids: list[str] = Field(default_factory=list)
    summary: str = ""


class MeetingUploadedPayload(BaseModel):
    """meeting.uploaded event payload."""

    model_config = ConfigDict(strict=True)

    content: str = Field(..., min_length=1)
    source: str = "event"
    title: str | None = None
    meeting_date: str | None = None
    participants: list[str] = Field(default_factory=list)
    context: str | None = None
    source_id: str | None = None


# ============ Development, testing, and delivery events ============

class CodeReviewedPayload(BaseModel):
    """code.reviewed event payload."""

    model_config = ConfigDict(strict=True)

    agent_name: str = ""
    commit_sha: str | None = Field(default=None, min_length=7, max_length=40)
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    review_status: Literal["approved", "changes_requested", "commented", "unknown"] = "unknown"
    findings: list[dict] = Field(default_factory=list)


class FeatureCompletedPayload(BaseModel):
    """feature.completed event payload."""

    model_config = ConfigDict(strict=True)

    feature_id: str | None = None
    title: str = ""
    completed_by: str | None = None
    artifact_links: list[str] = Field(default_factory=list)
    summary: str = ""


class TestResultPayload(BaseModel):
    """test.passed / test.failed event payload."""

    model_config = ConfigDict(strict=True)

    test_run_id: str | None = None
    suite: str = ""
    status: Literal["passed", "failed"] | None = None
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    report_uri: str | None = None


class DeploymentEventPayload(BaseModel):
    """deployment.started / deployment.completed event payload."""

    model_config = ConfigDict(strict=True)

    deployment_id: str | None = None
    environment: str = ""
    version: str | None = None
    status: Literal["started", "completed", "failed", "unknown"] = "unknown"
    started_by: str | None = None
    artifact_links: list[str] = Field(default_factory=list)


# ============ Operations and customer events ============

class DeviceEventPayload(BaseModel):
    """device.online / device.offline / device.alert event payload."""

    model_config = ConfigDict(strict=True)

    device_id: str | None = None
    status: Literal["online", "offline", "alert", "unknown"] = "unknown"
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"
    message: str = ""
    metadata: dict = Field(default_factory=dict)


class LeadQualifiedPayload(BaseModel):
    """lead.qualified event payload."""

    model_config = ConfigDict(strict=True)

    lead_id: str | None = None
    source_system: str = ""
    qualification_score: float | None = Field(default=None, ge=0, le=1)
    owner: str | None = None
    summary: str = ""


class DealWonPayload(BaseModel):
    """deal.won event payload."""

    model_config = ConfigDict(strict=True)

    deal_id: str | None = None
    customer_id: str | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    owner: str | None = None


class TicketCreatedPayload(BaseModel):
    """ticket.created event payload."""

    model_config = ConfigDict(strict=True)

    ticket_id: str | None = None
    customer_id: str | None = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    subject: str = ""
    source_system: str = ""


# ============ Control-plane ledger events ============

class CompanyEventPayload(BaseModel):
    """company.created / company.updated event payload."""

    model_config = ConfigDict(strict=True)

    company_id: str
    trace_id: str | None = None
    name: str
    mission: str = ""


class ControlPlaneReferencePayload(BaseModel):
    """Shared references for control-plane events."""

    model_config = ConfigDict(strict=True)

    company_id: str
    trace_id: str | None = None
    goal_id: str | None = None
    work_item_id: str | None = None
    run_id: str | None = None


class GoalEventPayload(ControlPlaneReferencePayload):
    """goal.created / goal.updated event payload."""

    goal_id: str
    title: str
    status: Literal["draft", "active", "paused", "completed", "cancelled"]
    parent_goal_id: str | None = None
    owner_agent_id: str | None = None
    owner_user_id: str | None = None
    current_value: float | None = None
    target_value: float | None = None


class WorkItemEventPayload(ControlPlaneReferencePayload):
    """work_item.created / work_item.updated event payload."""

    work_item_id: str
    title: str
    status: Literal[
        "queued",
        "ready",
        "running",
        "blocked",
        "awaiting_approval",
        "completed",
        "failed",
        "cancelled",
    ]
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    owner_agent_id: str | None = None
    owner_user_id: str | None = None
    source: str = "manual"
    external_ref: str | None = None


class DecisionEventPayload(ControlPlaneReferencePayload):
    """decision.created / decision.updated event payload."""

    decision_id: str
    title: str
    status: Literal["proposed", "accepted", "rejected", "superseded"]
    selected_option: str | None = None
    decided_by: str | None = None


class ArtifactEventPayload(ControlPlaneReferencePayload):
    """artifact.created event payload."""

    artifact_id: str
    artifact_type: Literal[
        "prd",
        "report",
        "qa_result",
        "issue",
        "merge_request",
        "code_patch",
        "run_walkthrough",
        "other",
    ]
    title: str
    uri: str
    created_by_agent_id: str | None = None


class AgentWakeupRequestedPayload(ControlPlaneReferencePayload):
    """agent.wakeup-requested event payload."""

    agent_id: str
    actor_id: str
    input: dict = Field(default_factory=dict)


class AgentWakeupCompletedPayload(ControlPlaneReferencePayload):
    """agent.wakeup-completed event payload."""

    agent_id: str
    status: Literal["succeeded", "failed"]
    output: dict = Field(default_factory=dict)
    error_category: str | None = None
    error_message: str | None = None


class AgentRunLifecyclePayload(ControlPlaneReferencePayload):
    """agent_run.started/succeeded/failed event payload."""

    agent_id: str
    status: Literal["running", "succeeded", "failed"]
    adapter_type: str | None = None
    error_category: str | None = None
    error_message: str | None = None


class AgentRoleCreatedPayload(ControlPlaneReferencePayload):
    """agent_role.created event payload."""

    agent_id: str
    role_id: str | None = None
    agent_kind: str
    interaction_mode: str
    role: str = ""
    adapter_type: str | None = None
    reports_to_agent_id: str | None = None


class AgentRoleStatusUpdatedPayload(ControlPlaneReferencePayload):
    """agent_role.status-updated event payload."""

    agent_id: str
    status: str
    actor_id: str | None = None


class ApprovalEventPayload(ControlPlaneReferencePayload):
    """approval.requested/granted/rejected event payload."""

    approval_id: str
    category: Literal["finance", "legal", "customer", "technical"]
    status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    requested_by: str
    source_agent_id: str
    proposed_action: str
    reason: str
    risk: str
    rollback_note: str
    affected_resources: list[str] = Field(min_length=1)
    artifact_links: list[str] = Field(default_factory=list)
    resolved_by: str | None = None


class BudgetUsageRecordedPayload(ControlPlaneReferencePayload):
    """budget.usage-recorded event payload."""

    usage_id: str
    budget_id: str
    scope: Literal["company", "goal", "agent", "work_item"] | None = None
    scope_id: str | None = None
    period: Literal["daily", "monthly", "quarterly", "total"] | None = None
    cost_usd: float = Field(..., ge=0)
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class AuditEventRecordedPayload(ControlPlaneReferencePayload):
    """audit.event-recorded event payload."""

    audit_event_id: str
    action: str
    target_type: str
    target_id: str
    actor_type: str
    actor_id: str
    idempotency_key: str | None = None
    detail: dict = Field(default_factory=dict)


class EvolutionProposalEventPayload(ControlPlaneReferencePayload):
    """evolution_proposal.created / updated event payload."""

    proposal_id: str
    tier: Literal["L1", "L2", "L3"]
    scope: str
    approval_state: Literal[
        "pending",
        "approved",
        "rejected",
        "expired",
        "cancelled",
    ]
    rollout_state: Literal[
        "proposed",
        "shadow",
        "canary",
        "active",
        "rolled_back",
        "rejected",
    ]
    approval_id: str | None = None


class EvolutionCycleTriggeredPayload(BaseModel):
    """evolution.cycle-triggered event payload."""

    model_config = ConfigDict(strict=True)

    days: int = Field(default=7, ge=1)


class EvolutionSkillProposedPayload(BaseModel):
    """evolution.skill-proposed event payload."""

    model_config = ConfigDict(strict=True)

    operation: str
    target_agent: str
    target_skill: str | None = None
    description: str = ""
    rationale: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    control_plane_approval_id: str | None = None


class EvolutionHumanFeedbackPayload(BaseModel):
    """evolution.human-feedback event payload."""

    model_config = ConfigDict(strict=True)

    approved: bool = False
    approval_id: str | None = None
    control_plane_approval_id: str | None = None
    user_id: str | None = None
    resolved_by: str | None = None


class EvolutionPatternProposedPayload(BaseModel):
    """evolution.pattern-proposed event payload."""

    model_config = ConfigDict(strict=True)

    pattern_id: str
    name: str
    trigger_event: str
    steps: list[dict] = Field(default_factory=list)
    control_plane_approval_id: str | None = None


class EvolutionPatternApprovedPayload(BaseModel):
    """evolution.pattern-approved event payload."""

    model_config = ConfigDict(strict=True)

    pattern_id: str
    approved: bool = False
    user_id: str | None = None
    approval_id: str | None = None
    control_plane_approval_id: str | None = None


class EvolutionPatternShadowCompletePayload(BaseModel):
    """evolution.pattern-shadow-complete event payload."""

    model_config = ConfigDict(strict=True)

    pattern_id: str
    shadow_run_id: str | None = None
    success: bool = False
    evidence: dict = Field(default_factory=dict)
    risk: str = ""


class ExecutionTracedPayload(BaseModel):
    """execution.traced event payload."""

    model_config = ConfigDict(strict=True)

    trace_id: str
    agent_id: str | None = None
    run_id: str | None = None
    summary: str = ""
    evidence: dict = Field(default_factory=dict)


class DLQFailedPayload(BaseModel):
    """dlq.failed payload for failed or malformed events."""

    original_event_id: str | None = None
    original_event_type: str | None = None
    original_source: str | None = None
    original_payload: dict = Field(default_factory=dict)
    failed_by_agent: str
    failure_stage: Literal["handler", "validation"]
    error: str


# ============ PM Sync Events ============

SyncScope = Literal["full", "openproject", "feishu_bitable"]
SyncTriggerScope = Literal["full", "openproject", "feishu_bitable", "feishu-bitable"]


class SyncTriggerPayload(BaseModel):
    """sync.trigger event payload."""

    model_config = ConfigDict(strict=True)

    triggered_by: str = "event"
    scope: SyncTriggerScope | None = None
    target: SyncTriggerScope | None = None


class SyncStartedPayload(BaseModel):
    """sync.started event payload."""

    model_config = ConfigDict(strict=True)

    triggered_by: str
    scope: SyncScope = "full"


class SyncCompletedPayload(BaseModel):
    """sync.completed event payload."""

    model_config = ConfigDict(strict=True)

    synced_count: int = Field(default=0, ge=0)
    scope: SyncScope = "full"
    errors: list[str] = Field(default_factory=list)


class SyncFailedPayload(BaseModel):
    """sync.failed event payload."""

    model_config = ConfigDict(strict=True)

    error: str
    scope: str = "unknown"


# ============ Analysis Report Events ============

class ReportGeneratedPayload(BaseModel):
    """report.daily-generated / report.weekly-generated event payload."""
    date: str = ""
    summary: str = ""


class RiskDetectedPayload(BaseModel):
    """analysis.risk-detected event payload."""
    risks: list[dict] = []


class QualityEvaluatedPayload(BaseModel):
    """analysis.quality-evaluated event payload."""

    model_config = ConfigDict(strict=True)

    evaluations: list[dict] = Field(default_factory=list)


# ============ PM Alert Events ============

class AlertTriggeredPayload(BaseModel):
    """pm.alert-triggered event payload."""
    alert_count: int = 0
    alerts: list[dict] = []
    push_ok: bool = False


# ============ Chat Events ============

class ChatPmQueryPayload(BaseModel):
    """chat.pm-query event payload."""
    user_id: str
    query: str = ""


class ChatPmResponsePayload(BaseModel):
    """chat.pm-response event payload."""
    user_id: str
    response: dict = {}


# ============ Coordinator Events ============

class CoordinatorDispatchPayload(BaseModel):
    """coordinator.dispatch event payload."""

    model_config = ConfigDict(strict=True)

    target_agent: str
    task_id: str | None = None
    instruction: str = ""
    workflow_id: str | None = None
    scratchpad_ref: str | None = None
    permissions: dict = Field(default_factory=dict)


# ============ A2A Bridge Events ============

class A2ATaskArtifactPayload(BaseModel):
    """A2A task artifact reference embedded in bridge result events."""

    model_config = ConfigDict(strict=True)

    artifact_id: str
    name: str
    description: str | None = None


class A2ATaskEventPayload(BaseModel):
    """a2a.task.* event payload for A2A task state transitions."""

    model_config = ConfigDict(strict=True)

    task_id: str
    context_id: str
    status: Literal[
        "submitted",
        "working",
        "input-required",
        "completed",
        "failed",
        "canceled",
    ]
    artifacts: list[A2ATaskArtifactPayload] = Field(default_factory=list)
    message: str | None = None


class A2ATaskErrorPayload(BaseModel):
    """a2a.task.error payload for A2A bridge failures."""

    model_config = ConfigDict(strict=True)

    error: str
    original_event_type: str


# ============ PM Task Decomposition Events ============

class SyncTaskNeedsDecomposePayload(BaseModel):
    """sync.task-needs-decompose event payload."""
    wp_id: int
    subject: str
    description: str = ""
    wp_type: str
    project_id: int
    project_name: str = ""
    assignee: str = ""
    assignee_id: int | None = None


class PMDecomposeCompletedPayload(BaseModel):
    """pm.decompose-completed event payload."""
    wp_id: int
    status: str
    user_story_count: int = 0
    task_count: int = 0


class PMDecompositionFailedPayload(BaseModel):
    """pm.decomposition-failed event payload."""

    model_config = ConfigDict(strict=True)

    error: str
    requirement_title: str = ""
    trace_id: str | None = None


class PMApprovalTimeoutPayload(BaseModel):
    """pm.approval-timeout event payload."""

    model_config = ConfigDict(strict=True)

    record_id: str
    age_hours: float = Field(..., ge=0)


class PMPrdReadyPayload(BaseModel):
    """pm.prd-ready event payload."""

    model_config = ConfigDict(strict=True)

    requirement_id: str | None = None
    prd_id: str | None = None
    title: str = ""
    prd_uri: str | None = None
    summary: str = ""
    workflow_id: str | None = None


# ============ QA Acceptance Events ============

class AcceptanceFindingPayload(BaseModel):
    """Single acceptance finding."""
    model_config = ConfigDict(strict=True)

    level: Literal["L0", "L1", "L2"] = Field(..., description="Check level")
    category: str = Field(..., description="security/architecture/quality/...")
    check: str = Field(..., description="Check name")
    status: Literal["PASS", "FAIL", "WARN", "INFO", "SKIP"] = Field(..., description="Check status")
    details: str | None = Field(default=None, description="Details")
    file: str | None = Field(default=None, description="File path")
    line: int | None = Field(default=None, description="Line number")
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        default="info", description="Severity"
    )
    is_blocking: bool = Field(default=False, description="Whether this triggers gate failure")


class AcceptanceSummaryPayload(BaseModel):
    """Acceptance summary."""
    model_config = ConfigDict(strict=True)

    l0_gate: Literal["PASS", "FAIL", "ERROR"] = Field(..., description="L0 gate status")
    l1_check: Literal["PASS", "WARN", "ERROR"] = Field(..., description="L1 check status")
    l2_report: Literal["INFO"] = Field(default="INFO")
    total_checks: int = Field(default=0, ge=0)
    l0_failures: int = Field(default=0, ge=0)
    l1_warnings: int = Field(default=0, ge=0)


class CodeCommittedPayload(BaseModel):
    """code.committed event payload."""
    model_config = ConfigDict(strict=True)

    agent_name: str = Field(..., pattern=r"^[a-z][a-z0-9_-]*$")
    commit_sha: str = Field(..., min_length=7, max_length=40)
    files_changed: list[str] = Field(default_factory=list)
    branch: str | None = None
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    diff_ref: str | None = None
    triggered_by: str = "event"


class QARunRequestedPayload(BaseModel):
    """qa.run-requested event payload."""
    model_config = ConfigDict(strict=True)

    agent_name: str = Field(..., pattern=r"^[a-z][a-z0-9_-]*$")
    level: str = Field(default="all", description="l0/l1/l2/all")
    commit_sha: str | None = Field(default=None, min_length=7, max_length=40)
    files_changed: list[str] = Field(default_factory=list)
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    requested_by: str = Field(default="system")
    reason: str | None = None


class QAAcceptanceCompletedPayload(BaseModel):
    """qa.acceptance-completed event payload."""
    model_config = ConfigDict(strict=True)

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    mr_iid: int | None = None
    gitlab_project_id: int | None = None
    trigger: str = Field(..., description="event/manual/api/scheduled")
    level: str = Field(default="all")
    target: str = Field(default="")
    summary: AcceptanceSummaryPayload
    findings: list[AcceptanceFindingPayload] = Field(default_factory=list)
    duration_seconds: float = Field(default=0, ge=0)
    report_markdown: str | None = None
    notification_summary: dict = Field(default_factory=dict)
    completed_at: str = Field(default="", description="ISO 8601")


class QAGateFailedPayload(BaseModel):
    """qa.gate-failed event payload."""
    model_config = ConfigDict(strict=True)

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    mr_iid: int | None = None
    gitlab_project_id: int | None = None
    l0_failure_count: int = Field(..., ge=0)
    blocking_findings: list[AcceptanceFindingPayload] = Field(
        default_factory=list,
    )
    duration_seconds: float = Field(default=0, ge=0)
    report_markdown: str | None = None


# ============ Dev Agent Events ============

class DevTaskInfo(BaseModel):
    """Development task information nested in task lists."""
    model_config = ConfigDict(strict=True)

    id: int = Field(..., description="Task ID (OP work package ID)")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    estimated_hours: float = Field(default=8, ge=0, le=100, description="Estimated hours")
    parent_story: str = Field(default="", description="Parent User Story")
    related_files: list[str] = Field(default_factory=list, description="Related file paths")


class PMTasksReadyForDevPayload(BaseModel):
    """pm.tasks-ready-for-dev event payload."""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    tasks: list[DevTaskInfo] = Field(..., description="Tasks ready for development", min_length=1)


class DevWorkflowCreatedPayload(BaseModel):
    """dev.workflow-created event payload."""
    model_config = ConfigDict(strict=True)

    task_id: str = Field(..., description="Task ID")
    workflow_id: str = Field(..., description="Workflow ID")
    node_count: int = Field(..., ge=1, description="Workflow node count")


class DevWorkflowCompletedPayload(BaseModel):
    """dev.workflow-completed event payload."""
    model_config = ConfigDict(strict=True)

    task_id: str = Field(..., description="Task ID")
    workflow_id: str = Field(..., description="Workflow ID")
    duration_s: float = Field(..., ge=0, description="Execution duration in seconds")


class DevMRCreatedPayload(BaseModel):
    """dev.mr-created event payload."""
    model_config = ConfigDict(strict=True)

    mr_url: str = Field(..., description="MR URL")
    wp_id: int = Field(..., description="Work Package ID")
    branch: str = Field(..., description="Branch name")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="MEDIUM", description="Risk level"
    )


class DevTaskCompletedPayload(BaseModel):
    """dev.task-completed event payload."""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    mr_url: str = Field(..., description="MR URL")
    duration_s: float = Field(..., ge=0, description="Execution duration in seconds")


class DevTaskFailedPayload(BaseModel):
    """dev.task-failed event payload."""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    error: str = Field(..., description="Error message")
    failed_node: str | None = Field(default=None, description="Failed workflow node")
    runbook_url: str | None = Field(default=None, description="Runbook URL")


# ============ Event Type to Payload Model Mapping ============

EVENT_PAYLOAD_MODELS = {
    "requirement.extracted": RequirementExtractedPayload,
    "requirement.confirmed": RequirementConfirmedPayload,
    "requirement.rejected": RequirementRejectedPayload,
    "requirement.changed": RequirementChangedPayload,
    "requirement.deleted": RequirementDeletedPayload,
    "project.created": ProjectEventPayload,
    "project.updated": ProjectEventPayload,
    "sprint.started": SprintStartedPayload,
    "sprint.completed": SprintCompletedPayload,
    "meeting.uploaded": MeetingUploadedPayload,
    "code.reviewed": CodeReviewedPayload,
    "feature.completed": FeatureCompletedPayload,
    "test.passed": TestResultPayload,
    "test.failed": TestResultPayload,
    "deployment.started": DeploymentEventPayload,
    "deployment.completed": DeploymentEventPayload,
    "device.online": DeviceEventPayload,
    "device.offline": DeviceEventPayload,
    "device.alert": DeviceEventPayload,
    "lead.qualified": LeadQualifiedPayload,
    "deal.won": DealWonPayload,
    "ticket.created": TicketCreatedPayload,
    "company.created": CompanyEventPayload,
    "company.updated": CompanyEventPayload,
    "goal.created": GoalEventPayload,
    "goal.updated": GoalEventPayload,
    "work_item.created": WorkItemEventPayload,
    "work_item.updated": WorkItemEventPayload,
    "decision.created": DecisionEventPayload,
    "decision.updated": DecisionEventPayload,
    "artifact.created": ArtifactEventPayload,
    "agent.wakeup-requested": AgentWakeupRequestedPayload,
    "agent.wakeup-completed": AgentWakeupCompletedPayload,
    "agent_run.started": AgentRunLifecyclePayload,
    "agent_run.succeeded": AgentRunLifecyclePayload,
    "agent_run.failed": AgentRunLifecyclePayload,
    "agent_role.created": AgentRoleCreatedPayload,
    "agent_role.status-updated": AgentRoleStatusUpdatedPayload,
    "approval.requested": ApprovalEventPayload,
    "approval.granted": ApprovalEventPayload,
    "approval.rejected": ApprovalEventPayload,
    "budget.usage-recorded": BudgetUsageRecordedPayload,
    "audit.event-recorded": AuditEventRecordedPayload,
    "evolution_proposal.created": EvolutionProposalEventPayload,
    "evolution_proposal.updated": EvolutionProposalEventPayload,
    "evolution.cycle-triggered": EvolutionCycleTriggeredPayload,
    "evolution.skill-proposed": EvolutionSkillProposedPayload,
    "evolution.human-feedback": EvolutionHumanFeedbackPayload,
    "evolution.pattern-proposed": EvolutionPatternProposedPayload,
    "evolution.pattern-approved": EvolutionPatternApprovedPayload,
    "evolution.pattern-shadow-complete": EvolutionPatternShadowCompletePayload,
    "execution.traced": ExecutionTracedPayload,
    "dlq.failed": DLQFailedPayload,
    "sync.trigger": SyncTriggerPayload,
    "sync.started": SyncStartedPayload,
    "sync.completed": SyncCompletedPayload,
    "sync.failed": SyncFailedPayload,
    "report.daily-generated": ReportGeneratedPayload,
    "report.weekly-generated": ReportGeneratedPayload,
    "analysis.risk-detected": RiskDetectedPayload,
    "analysis.quality-evaluated": QualityEvaluatedPayload,
    "pm.alert-triggered": AlertTriggeredPayload,
    "chat.pm-query": ChatPmQueryPayload,
    "chat.pm-response": ChatPmResponsePayload,
    "coordinator.command": CoordinatorCommand,
    "coordinator.response": CoordinatorResponse,
    "coordinator.dispatch": CoordinatorDispatchPayload,
    "task.notification": TaskNotification,
    "task.progress": AgentProgress,
    "a2a.task.submitted": A2ATaskEventPayload,
    "a2a.task.working": A2ATaskEventPayload,
    "a2a.task.input-required": A2ATaskEventPayload,
    "a2a.task.completed": A2ATaskEventPayload,
    "a2a.task.failed": A2ATaskEventPayload,
    "a2a.task.canceled": A2ATaskEventPayload,
    "a2a.task.error": A2ATaskErrorPayload,
    "sync.task-needs-decompose": SyncTaskNeedsDecomposePayload,
    "pm.decompose-completed": PMDecomposeCompletedPayload,
    "pm.decomposition-failed": PMDecompositionFailedPayload,
    "pm.approval-timeout": PMApprovalTimeoutPayload,
    "pm.prd-ready": PMPrdReadyPayload,
    "code.committed": CodeCommittedPayload,
    "qa.run-requested": QARunRequestedPayload,
    "qa.acceptance-completed": QAAcceptanceCompletedPayload,
    "qa.gate-failed": QAGateFailedPayload,
    "pm.tasks-ready-for-dev": PMTasksReadyForDevPayload,
    "dev.workflow-created": DevWorkflowCreatedPayload,
    "dev.workflow-completed": DevWorkflowCompletedPayload,
    "dev.mr-created": DevMRCreatedPayload,
    "dev.task-completed": DevTaskCompletedPayload,
    "dev.task-failed": DevTaskFailedPayload,
}


def validate_event_payload(event_type: str, payload: dict) -> BaseModel:
    """
    Validate an event payload against its contract.

    Args:
        event_type: Event type.
        payload: Event payload.

    Returns:
        Validated Pydantic model.

    Raises:
        KeyError: Unknown event type.
        ValidationError: Payload does not match the contract.
    """
    model = EVENT_PAYLOAD_MODELS.get(event_type)
    if model is None:
        raise KeyError(f"Unknown event type: {event_type}")
    return model.model_validate(payload)
