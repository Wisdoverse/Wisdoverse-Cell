"""
Event Schema - standard format for inter-agent communication.

All inter-agent communication flows through Event objects. Events are the
shared language of the system.
"""
import math
import re
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.core.ids import generate_id

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)+$")
_AGENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def validate_agent_id(agent_id: str, *, field_name: str = "agent_id") -> str:
    """Validate stable runtime agent IDs used in events and agent contracts."""
    if not _AGENT_ID_PATTERN.fullmatch(agent_id):
        raise ValueError(f"{field_name} must be a stable runtime agent ID")
    return agent_id


class _ReadOnlyDict(dict):
    """dict-compatible read-only mapping for event payloads."""

    def _read_only(self, *args, **kwargs):
        raise TypeError("Event payload is immutable")

    __setitem__ = _read_only
    __delitem__ = _read_only
    clear = _read_only
    pop = _read_only
    popitem = _read_only
    setdefault = _read_only
    update = _read_only
    __ior__ = _read_only


class _ReadOnlyList(list):
    """list-compatible read-only sequence for nested event payload values."""

    def _read_only(self, *args, **kwargs):
        raise TypeError("Event payload is immutable")

    __setitem__ = _read_only
    __delitem__ = _read_only
    append = _read_only
    clear = _read_only
    extend = _read_only
    insert = _read_only
    pop = _read_only
    remove = _read_only
    reverse = _read_only
    sort = _read_only
    __iadd__ = _read_only
    __imul__ = _read_only


def _freeze_json_value(value: Any, *, path: str = "payload") -> Any:
    if isinstance(value, dict):
        return _ReadOnlyDict(
            {
                str(key): _freeze_json_value(item, path=f"{path}.{key}")
                for key, item in value.items()
            }
        )
    if isinstance(value, list | tuple):
        return _ReadOnlyList(
            _freeze_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return value
    raise ValueError(f"{path} contains non-JSON-serializable value {type(value).__name__}")


class EventMetadata(BaseModel):
    """Event metadata."""
    model_config = ConfigDict(frozen=True)

    trace_id: Optional[str] = None      # trace ID for a related event chain
    retry_count: int = 0                 # retry count
    correlation_id: Optional[str] = None # correlation ID for request-response flows

    @field_validator("retry_count")
    @classmethod
    def _validate_retry_count(cls, retry_count: int) -> int:
        if retry_count < 0:
            raise ValueError("retry_count must be greater than or equal to 0")
        return retry_count


class Event(BaseModel):
    """
    Standard event format.

    Event type naming convention: {domain}.{action}
    - requirement.extracted  requirement extracted
    - requirement.confirmed  requirement confirmed
    - requirement.changed    requirement changed
    - code.committed         code committed
    - test.passed            test passed
    - device.alert           device alert
    """

    model_config = ConfigDict(
        frozen=True,
        ser_json_timedelta="iso8601",
    )

    # Required fields
    event_id: str = Field(default_factory=lambda: generate_id("evt"))
    event_type: str                      # format: {domain}.{action}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_agent: str                    # emitting agent ID
    payload: dict[str, Any]              # event payload
    schema_version: str = "1.0"          # schema version for forward compatibility

    # Optional fields
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, event_id: str) -> str:
        """Require a stable explicit event identifier when one is provided."""
        if not event_id.strip():
            raise ValueError("event_id must be a stable non-empty identifier")
        return event_id

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, event_type: str) -> str:
        """Enforce the cross-agent event naming contract: {domain}.{action}."""
        if not _EVENT_TYPE_PATTERN.fullmatch(event_type):
            raise ValueError("event_type must use {domain}.{action} naming")
        return event_type

    @field_validator("source_agent")
    @classmethod
    def _validate_source_agent(cls, source_agent: str) -> str:
        """Require an explicit publishing agent ID."""
        return validate_agent_id(source_agent, field_name="source_agent")

    @field_validator("payload", mode="after")
    @classmethod
    def _freeze_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Store event payloads as recursive read-only JSON-like data."""
        return _freeze_json_value(payload)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, schema_version: str) -> str:
        """Require a non-empty schema version in every serialized event."""
        if not schema_version.strip():
            raise ValueError("schema_version must be present")
        return schema_version

    @classmethod
    def create(
        cls,
        event_type: str,
        source_agent: str,
        payload: dict[str, Any],
        trace_id: Optional[str] = None
    ) -> "Event":
        """Create an event with standard metadata."""
        return cls(
            event_type=event_type,
            source_agent=source_agent,
            payload=payload,
            metadata=EventMetadata(trace_id=trace_id)
        )


# Predefined event type constants
class EventTypes:
    """Event type constants."""

    # Requirements
    REQUIREMENT_EXTRACTED = "requirement.extracted"
    REQUIREMENT_CONFIRMED = "requirement.confirmed"
    REQUIREMENT_CHANGED = "requirement.changed"
    REQUIREMENT_REJECTED = "requirement.rejected"
    REQUIREMENT_DELETED = "requirement.deleted"

    # External work context consumed by requirement manager
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    SPRINT_STARTED = "sprint.started"
    SPRINT_COMPLETED = "sprint.completed"
    MEETING_UPLOADED = "meeting.uploaded"

    # Development
    CODE_COMMITTED = "code.committed"
    CODE_REVIEWED = "code.reviewed"
    FEATURE_COMPLETED = "feature.completed"

    # Tests
    TEST_PASSED = "test.passed"
    TEST_FAILED = "test.failed"

    # Delivery
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_COMPLETED = "deployment.completed"

    # Operations
    DEVICE_ONLINE = "device.online"
    DEVICE_OFFLINE = "device.offline"
    DEVICE_ALERT = "device.alert"

    # Customer
    LEAD_QUALIFIED = "lead.qualified"
    DEAL_WON = "deal.won"
    TICKET_CREATED = "ticket.created"

    # Approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"

    # Control-plane ledger
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    DECISION_CREATED = "decision.created"
    DECISION_UPDATED = "decision.updated"
    AGENT_ROLE_CREATED = "agent_role.created"
    AGENT_ROLE_UPDATED = "agent_role.updated"
    AGENT_ROLE_STATUS_UPDATED = "agent_role.status-updated"
    AGENT_PROMPT_CONFIG_UPDATED = "agent.prompt-config-updated"
    AGENT_WAKEUP_REQUESTED = "agent.wakeup-requested"
    AGENT_WAKEUP_COMPLETED = "agent.wakeup-completed"
    AGENT_RUN_STARTED = "agent_run.started"
    AGENT_RUN_SUCCEEDED = "agent_run.succeeded"
    AGENT_RUN_FAILED = "agent_run.failed"
    BUDGET_POLICY_CREATED = "budget_policy.created"
    BUDGET_POLICY_UPDATED = "budget_policy.updated"
    BUDGET_USAGE_RECORDED = "budget.usage-recorded"
    ARTIFACT_CREATED = "artifact.created"
    AUDIT_EVENT_RECORDED = "audit.event-recorded"
    EVOLUTION_PROPOSAL_CREATED = "evolution_proposal.created"
    EVOLUTION_PROPOSAL_UPDATED = "evolution_proposal.updated"

    # PM sync
    SYNC_STARTED = "sync.started"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"
    SYNC_TRIGGER = "sync.trigger"

    # Analysis reports
    REPORT_DAILY_GENERATED = "report.daily-generated"
    REPORT_WEEKLY_GENERATED = "report.weekly-generated"
    ANALYSIS_RISK_DETECTED = "analysis.risk-detected"
    ANALYSIS_QUALITY_EVALUATED = "analysis.quality-evaluated"

    # PM alerts
    PM_ALERT_TRIGGERED = "pm.alert-triggered"

    # PM task decomposition
    SYNC_TASK_NEEDS_DECOMPOSE = "sync.task-needs-decompose"
    PM_DECOMPOSE_COMPLETED = "pm.decompose-completed"
    PM_DECOMPOSITION_FAILED = "pm.decomposition-failed"
    PM_APPROVAL_TIMEOUT = "pm.approval-timeout"

    # QA acceptance
    QA_RUN_REQUESTED = "qa.run-requested"
    QA_ACCEPTANCE_COMPLETED = "qa.acceptance-completed"
    QA_GATE_FAILED = "qa.gate-failed"

    # Chat
    CHAT_PM_QUERY = "chat.pm-query"
    CHAT_PM_RESPONSE = "chat.pm-response"

    # Evolution system
    EXECUTION_TRACED = "execution.traced"
    EVOLUTION_CYCLE_TRIGGERED = "evolution.cycle-triggered"
    EVOLUTION_SKILL_PROPOSED = "evolution.skill-proposed"
    EVOLUTION_HUMAN_FEEDBACK = "evolution.human-feedback"

    # Collaboration events
    EVOLUTION_PATTERN_PROPOSED = "evolution.pattern-proposed"
    EVOLUTION_PATTERN_APPROVED = "evolution.pattern-approved"
    EVOLUTION_PATTERN_SHADOW_COMPLETE = "evolution.pattern-shadow-complete"

    # Dead Letter Queue
    DLQ_FAILED = "dlq.failed"

    # Dev Agent
    PM_TASKS_READY_FOR_DEV = "pm.tasks-ready-for-dev"
    DEV_WORKFLOW_CREATED = "dev.workflow-created"
    DEV_WORKFLOW_COMPLETED = "dev.workflow-completed"
    DEV_MR_CREATED = "dev.mr-created"
    DEV_TASK_COMPLETED = "dev.task-completed"
    DEV_TASK_FAILED = "dev.task-failed"

    # Coordinator orchestration
    COORDINATOR_COMMAND = "coordinator.command"
    COORDINATOR_RESPONSE = "coordinator.response"
    COORDINATOR_DISPATCH = "coordinator.dispatch"
    TASK_NOTIFICATION = "task.notification"
    TASK_PROGRESS = "task.progress"
    PM_PRD_READY = "pm.prd-ready"

    # A2A bridge
    A2A_TASK_SUBMITTED = "a2a.task.submitted"
    A2A_TASK_WORKING = "a2a.task.working"
    A2A_TASK_INPUT_REQUIRED = "a2a.task.input-required"
    A2A_TASK_COMPLETED = "a2a.task.completed"
    A2A_TASK_FAILED = "a2a.task.failed"
    A2A_TASK_CANCELED = "a2a.task.canceled"
    A2A_TASK_ERROR = "a2a.task.error"
