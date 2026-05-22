"""Typed identifier value-object wrappers for the Wisdoverse Cell backend.

Seeds the DDD identifier value-object pattern per
``architecture-principles.md`` §4.9 and ``ddd-compliance-audit.md`` row
DDD-007.

The wrappers are `typing.NewType` aliases: at runtime they are plain
``str`` (zero overhead), but the static type checker treats each
identifier as a distinct type. That means a function that takes a
``WorkItemId`` cannot silently accept a ``GoalId`` or a raw ``str``,
catching identifier-mix bugs that the previous string-typed signatures
could not detect.

Adoption pattern (one PR per identifier so changes stay reviewable):

1. Pick one identifier from the catalogue below.
2. Update the function signatures that produce or consume it
   (`<aggregate>_store.py`, `<aggregate>_use_cases.py`, application
   facades).
3. Update tests to construct identifiers via the constructor wrapper
   (e.g. ``WorkItemId("work_01hq...")``).
4. Let mypy / pyright flag remaining call sites.

The wrappers below cover the canonical product objects owned by the
Control Plane (`docs/architecture/data-ownership.md` §1) plus a small
set of business-runtime identifiers. Extend per row as Stage 2
aggregates land.
"""

from __future__ import annotations

from typing import NewType

from shared.core.ids import IDPrefix, generate_id

# Control Plane / Governance identifiers (per shared/control_plane/models.py).
CompanyId = NewType("CompanyId", str)
GoalId = NewType("GoalId", str)
AgentRoleId = NewType("AgentRoleId", str)
WorkItemId = NewType("WorkItemId", str)
AgentRunId = NewType("AgentRunId", str)
DecisionId = NewType("DecisionId", str)
ApprovalRequestId = NewType("ApprovalRequestId", str)
ArtifactId = NewType("ArtifactId", str)
BudgetPolicyId = NewType("BudgetPolicyId", str)
BudgetUsageId = NewType("BudgetUsageId", str)
AuditEventId = NewType("AuditEventId", str)
EvolutionProposalId = NewType("EvolutionProposalId", str)
AgentPromptConfigId = NewType("AgentPromptConfigId", str)

# Business runtime identifiers.
RequirementId = NewType("RequirementId", str)
MeetingId = NewType("MeetingId", str)
OpenQuestionId = NewType("OpenQuestionId", str)
FeedbackRecordId = NewType("FeedbackRecordId", str)
DevTaskId = NewType("DevTaskId", str)
AcceptanceRunId = NewType("AcceptanceRunId", str)

# Cross-cutting identifiers.
EventId = NewType("EventId", str)
TraceId = NewType("TraceId", str)
UserId = NewType("UserId", str)


def new_company_id() -> CompanyId:
    """Generate a fresh CompanyId."""
    return CompanyId(generate_id(IDPrefix.COMPANY))


def new_goal_id() -> GoalId:
    """Generate a fresh GoalId."""
    return GoalId(generate_id(IDPrefix.GOAL))


def new_work_item_id() -> WorkItemId:
    """Generate a fresh WorkItemId."""
    return WorkItemId(generate_id(IDPrefix.WORK_ITEM))


def new_agent_run_id() -> AgentRunId:
    """Generate a fresh AgentRunId."""
    return AgentRunId(generate_id(IDPrefix.AGENT_RUN))


def new_decision_id() -> DecisionId:
    """Generate a fresh DecisionId."""
    return DecisionId(generate_id(IDPrefix.DECISION))


def new_approval_id() -> ApprovalRequestId:
    """Generate a fresh ApprovalRequestId."""
    return ApprovalRequestId(generate_id(IDPrefix.APPROVAL))


def new_artifact_id() -> ArtifactId:
    """Generate a fresh ArtifactId."""
    return ArtifactId(generate_id(IDPrefix.ARTIFACT))


def new_budget_policy_id() -> BudgetPolicyId:
    """Generate a fresh BudgetPolicyId."""
    return BudgetPolicyId(generate_id(IDPrefix.BUDGET))


def new_budget_usage_id() -> BudgetUsageId:
    """Generate a fresh BudgetUsageId."""
    return BudgetUsageId(generate_id(IDPrefix.BUDGET_USAGE))


def new_audit_event_id() -> AuditEventId:
    """Generate a fresh AuditEventId."""
    return AuditEventId(generate_id(IDPrefix.AUDIT_EVENT))


def new_evolution_proposal_id() -> EvolutionProposalId:
    """Generate a fresh EvolutionProposalId."""
    return EvolutionProposalId(generate_id(IDPrefix.EVOLUTION_PROPOSAL))


def new_requirement_id() -> RequirementId:
    """Generate a fresh RequirementId."""
    return RequirementId(generate_id(IDPrefix.REQUIREMENT))


def new_meeting_id() -> MeetingId:
    """Generate a fresh MeetingId."""
    return MeetingId(generate_id(IDPrefix.MEETING))


def new_open_question_id() -> OpenQuestionId:
    """Generate a fresh OpenQuestionId."""
    return OpenQuestionId(generate_id(IDPrefix.QUESTION))


def new_event_id() -> EventId:
    """Generate a fresh EventId."""
    return EventId(generate_id(IDPrefix.EVENT))


__all__ = [
    "AcceptanceRunId",
    "AgentPromptConfigId",
    "AgentRoleId",
    "AgentRunId",
    "ApprovalRequestId",
    "ArtifactId",
    "AuditEventId",
    "BudgetPolicyId",
    "BudgetUsageId",
    "CompanyId",
    "DecisionId",
    "DevTaskId",
    "EventId",
    "EvolutionProposalId",
    "FeedbackRecordId",
    "GoalId",
    "MeetingId",
    "OpenQuestionId",
    "RequirementId",
    "TraceId",
    "UserId",
    "WorkItemId",
    "new_agent_run_id",
    "new_approval_id",
    "new_artifact_id",
    "new_audit_event_id",
    "new_budget_policy_id",
    "new_budget_usage_id",
    "new_company_id",
    "new_decision_id",
    "new_event_id",
    "new_evolution_proposal_id",
    "new_goal_id",
    "new_meeting_id",
    "new_open_question_id",
    "new_requirement_id",
    "new_work_item_id",
]
