"""
Event Payloads - payload contract definitions.

Defines payload formats for event contract tests and type checking. Agents can
use these models as the reference when subscribing to events.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


# ============ Control-plane ledger events ============

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


class ApprovalEventPayload(ControlPlaneReferencePayload):
    """approval.requested/granted/rejected event payload."""

    approval_id: str
    category: Literal["finance", "legal", "customer", "technical"]
    status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    requested_by: str
    source_agent_id: str
    proposed_action: str
    risk: str
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


# ============ PM Sync Events ============

class SyncCompletedPayload(BaseModel):
    """sync.completed event payload."""
    synced_count: int = 0
    errors: list[str] = []


class SyncFailedPayload(BaseModel):
    """sync.failed event payload."""
    error: str


# ============ Analysis Report Events ============

class ReportGeneratedPayload(BaseModel):
    """report.daily-generated / report.weekly-generated event payload."""
    date: str = ""
    summary: str = ""


class RiskDetectedPayload(BaseModel):
    """analysis.risk-detected event payload."""
    risks: list[dict] = []


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
    "approval.requested": ApprovalEventPayload,
    "approval.granted": ApprovalEventPayload,
    "approval.rejected": ApprovalEventPayload,
    "budget.usage-recorded": BudgetUsageRecordedPayload,
    "audit.event-recorded": AuditEventRecordedPayload,
    "sync.completed": SyncCompletedPayload,
    "sync.failed": SyncFailedPayload,
    "report.daily-generated": ReportGeneratedPayload,
    "report.weekly-generated": ReportGeneratedPayload,
    "analysis.risk-detected": RiskDetectedPayload,
    "pm.alert-triggered": AlertTriggeredPayload,
    "chat.pm-query": ChatPmQueryPayload,
    "chat.pm-response": ChatPmResponsePayload,
    "sync.task-needs-decompose": SyncTaskNeedsDecomposePayload,
    "pm.decompose-completed": PMDecomposeCompletedPayload,
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
