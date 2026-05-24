"""Audit collection boundary for Control Plane aggregate domain events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from shared.schemas.event import EventTypes

from .domain.agent_prompt_config import AgentPromptConfigUpdated
from .domain.agent_role import AgentRoleStatusChanged
from .domain.agent_run import AgentRunStatusChanged
from .domain.approval_request import ApprovalStatusChanged
from .domain.artifact import ArtifactCreated
from .domain.audit_event import clean_audit_detail
from .domain.budget_policy import BudgetPolicyCreated, BudgetPolicyUpdated
from .domain.budget_usage import BudgetUsageRecorded
from .domain.company_context import CompanyContextCreated, CompanyContextUpdated
from .domain.decision import DecisionStatusChanged
from .domain.events import ControlPlaneDomainEvent
from .domain.evolution_proposal import EvolutionRolloutStatusChanged
from .domain.goal import GoalStatusChanged
from .domain.work_item import WorkItemStatusChanged
from .models import AgentRunStatus, ApprovalStatus, AuditEvent


class ControlPlaneDomainEventAuditStore(Protocol):
    """Persistence port subset needed to append domain-event audits."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""


@dataclass(frozen=True, slots=True)
class DomainEventAuditContext:
    """Application context attached to audit records built from domain events."""

    actor_type: str = "system"
    actor_id: str = ""
    trace_id: str | None = None
    run_id: str | None = None
    work_item_id: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _AuditTarget:
    action: str
    target_type: str
    target_id: str


def audit_event_from_domain_event(
    event: ControlPlaneDomainEvent,
    context: DomainEventAuditContext,
) -> AuditEvent:
    """Build one durable AuditEvent from one aggregate-raised domain event."""
    target = _audit_target_for(event)
    detail = clean_audit_detail(event.to_payload())
    detail["domain_event"] = event.event_name
    detail.update(clean_audit_detail(context.detail))
    return AuditEvent(
        company_id=detail["company_id"],
        action=target.action,
        target_type=target.target_type,
        target_id=target.target_id,
        actor_type=context.actor_type,
        actor_id=context.actor_id,
        trace_id=context.trace_id,
        run_id=context.run_id,
        work_item_id=context.work_item_id,
        detail=detail,
    )


async def append_control_plane_domain_event_audits(
    store: ControlPlaneDomainEventAuditStore,
    events: Sequence[ControlPlaneDomainEvent],
    context: DomainEventAuditContext,
) -> list[AuditEvent]:
    """Append audit rows for aggregate-raised Control Plane domain events."""
    appended: list[AuditEvent] = []
    for event in events:
        appended.append(
            await store.append_audit_event(
                audit_event_from_domain_event(event, context),
            )
        )
    return appended


def _audit_target_for(event: ControlPlaneDomainEvent) -> _AuditTarget:
    if isinstance(event, AgentRunStatusChanged):
        return _AuditTarget(
            action=_agent_run_action(event.to_status),
            target_type="agent_run",
            target_id=event.run_id,
        )
    if isinstance(event, AgentRoleStatusChanged):
        return _AuditTarget(
            action=EventTypes.AGENT_ROLE_STATUS_UPDATED,
            target_type="agent_role",
            target_id=event.agent_id,
        )
    if isinstance(event, AgentPromptConfigUpdated):
        return _AuditTarget(
            action=EventTypes.AGENT_PROMPT_CONFIG_UPDATED,
            target_type="agent_prompt_config",
            target_id=event.agent_id,
        )
    if isinstance(event, ArtifactCreated):
        return _AuditTarget(
            action=EventTypes.ARTIFACT_CREATED,
            target_type="artifact",
            target_id=event.artifact_id,
        )
    if isinstance(event, BudgetPolicyCreated):
        return _AuditTarget(
            action=EventTypes.BUDGET_POLICY_CREATED,
            target_type="budget_policy",
            target_id=event.budget_id,
        )
    if isinstance(event, BudgetPolicyUpdated):
        return _AuditTarget(
            action=EventTypes.BUDGET_POLICY_UPDATED,
            target_type="budget_policy",
            target_id=event.budget_id,
        )
    if isinstance(event, BudgetUsageRecorded):
        return _AuditTarget(
            action=EventTypes.BUDGET_USAGE_RECORDED,
            target_type="budget_usage",
            target_id=event.usage_id,
        )
    if isinstance(event, CompanyContextCreated):
        return _AuditTarget(
            action=EventTypes.COMPANY_CREATED,
            target_type="company",
            target_id=event.company_id,
        )
    if isinstance(event, CompanyContextUpdated):
        return _AuditTarget(
            action=EventTypes.COMPANY_UPDATED,
            target_type="company",
            target_id=event.company_id,
        )
    if isinstance(event, ApprovalStatusChanged):
        return _AuditTarget(
            action=_approval_action(event.to_status),
            target_type="approval",
            target_id=event.approval_id,
        )
    if isinstance(event, DecisionStatusChanged):
        return _AuditTarget(
            action=EventTypes.DECISION_UPDATED,
            target_type="decision",
            target_id=event.decision_id,
        )
    if isinstance(event, EvolutionRolloutStatusChanged):
        return _AuditTarget(
            action=EventTypes.EVOLUTION_PROPOSAL_UPDATED,
            target_type="evolution_proposal",
            target_id=event.proposal_id,
        )
    if isinstance(event, GoalStatusChanged):
        return _AuditTarget(
            action=EventTypes.GOAL_UPDATED,
            target_type="goal",
            target_id=event.goal_id,
        )
    if isinstance(event, WorkItemStatusChanged):
        return _AuditTarget(
            action=EventTypes.WORK_ITEM_UPDATED,
            target_type="work_item",
            target_id=event.work_item_id,
        )
    raise TypeError(f"unsupported control-plane domain event: {type(event).__name__}")


def _agent_run_action(status: AgentRunStatus) -> str:
    if status == AgentRunStatus.RUNNING:
        return EventTypes.AGENT_RUN_STARTED
    if status == AgentRunStatus.SUCCEEDED:
        return EventTypes.AGENT_RUN_SUCCEEDED
    if status == AgentRunStatus.FAILED:
        return EventTypes.AGENT_RUN_FAILED
    return f"agent_run.{status.value}"


def _approval_action(status: ApprovalStatus) -> str:
    if status == ApprovalStatus.APPROVED:
        return EventTypes.APPROVAL_GRANTED
    if status == ApprovalStatus.REJECTED:
        return EventTypes.APPROVAL_REJECTED
    return f"approval.{status.value}"


__all__ = [
    "ControlPlaneDomainEventAuditStore",
    "DomainEventAuditContext",
    "append_control_plane_domain_event_audits",
    "audit_event_from_domain_event",
]
