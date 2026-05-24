"""Tests for Control Plane domain-event audit collection."""

import pytest

from shared.control_plane.domain.agent_prompt_config import AgentPromptConfigUpdated
from shared.control_plane.domain.agent_role import AgentRoleStatus, AgentRoleStatusChanged
from shared.control_plane.domain.agent_run import AgentRunStatusChanged
from shared.control_plane.domain.approval_request import ApprovalStatusChanged
from shared.control_plane.domain.artifact import ArtifactCreated
from shared.control_plane.domain.budget_policy import (
    BudgetPolicyCreated,
    BudgetPolicyStatus,
    BudgetPolicyUpdated,
)
from shared.control_plane.domain.budget_usage import BudgetUsageRecorded
from shared.control_plane.domain.company_context import (
    CompanyContextCreated,
    CompanyContextUpdated,
)
from shared.control_plane.domain.decision import DecisionStatusChanged
from shared.control_plane.domain.evolution_proposal import EvolutionRolloutStatusChanged
from shared.control_plane.domain.goal import GoalStatusChanged
from shared.control_plane.domain.work_item import WorkItemStatusChanged
from shared.control_plane.domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
    audit_event_from_domain_event,
)
from shared.control_plane.models import (
    AgentRunStatus,
    ApprovalStatus,
    AuditEvent,
    DecisionStatus,
    EvolutionRolloutState,
    GoalStatus,
    WorkItemStatus,
)
from shared.schemas.event import EventTypes


@pytest.mark.parametrize(
    ("event", "action", "target_type", "target_id"),
    [
        (
            ArtifactCreated(
                artifact_id="artifact_test",
                company_id="cmp_test",
                artifact_type="report",
                goal_id="goal_test",
                work_item_id="work_test",
                run_id="run_test",
                created_by_agent_id="dev-agent",
                has_content_hash=True,
            ),
            EventTypes.ARTIFACT_CREATED,
            "artifact",
            "artifact_test",
        ),
        (
            BudgetPolicyCreated(
                budget_id="budget_test",
                company_id="cmp_test",
                scope="agent",
                scope_id="dev-agent",
                period="daily",
                limit_usd=20,
                warning_threshold=0.8,
                status=BudgetPolicyStatus.ACTIVE,
                model_allowlist=("gpt-5",),
            ),
            EventTypes.BUDGET_POLICY_CREATED,
            "budget_policy",
            "budget_test",
        ),
        (
            BudgetPolicyUpdated(
                budget_id="budget_test",
                company_id="cmp_test",
                scope="agent",
                scope_id="dev-agent",
                period="daily",
                from_status=BudgetPolicyStatus.ACTIVE,
                to_status=BudgetPolicyStatus.PAUSED,
                changed_fields=("status",),
            ),
            EventTypes.BUDGET_POLICY_UPDATED,
            "budget_policy",
            "budget_test",
        ),
        (
            BudgetUsageRecorded(
                usage_id="usage_test",
                company_id="cmp_test",
                budget_id="budget_test",
                cost_usd=0.42,
                model="tool:agentforge_apply",
                input_tokens=10,
                output_tokens=5,
                run_id="run_test",
                trace_id="trace_test",
                metadata_keys=("tool",),
            ),
            EventTypes.BUDGET_USAGE_RECORDED,
            "budget_usage",
            "usage_test",
        ),
        (
            CompanyContextCreated(
                company_id="cmp_test",
                name_length=10,
                mission_length=20,
                metadata_keys=("stage",),
            ),
            EventTypes.COMPANY_CREATED,
            "company",
            "cmp_test",
        ),
        (
            CompanyContextUpdated(
                company_id="cmp_test",
                name_changed=True,
                mission_changed=False,
                metadata_changed=True,
                name_length=10,
                mission_length=20,
                metadata_keys=("stage",),
            ),
            EventTypes.COMPANY_UPDATED,
            "company",
            "cmp_test",
        ),
        (
            AgentPromptConfigUpdated(
                company_id="cmp_test",
                agent_id="requirement-manager",
                prompt_length=42,
                metadata_keys=("source",),
            ),
            EventTypes.AGENT_PROMPT_CONFIG_UPDATED,
            "agent_prompt_config",
            "requirement-manager",
        ),
        (
            AgentRoleStatusChanged(
                role_id="role_test",
                agent_id="ops-runner",
                company_id="cmp_test",
                from_status=AgentRoleStatus.ACTIVE,
                to_status=AgentRoleStatus.PAUSED,
            ),
            EventTypes.AGENT_ROLE_STATUS_UPDATED,
            "agent_role",
            "ops-runner",
        ),
        (
            AgentRunStatusChanged(
                run_id="run_test",
                agent_id="dev-agent",
                company_id="cmp_test",
                from_status=AgentRunStatus.RUNNING,
                to_status=AgentRunStatus.SUCCEEDED,
            ),
            EventTypes.AGENT_RUN_SUCCEEDED,
            "agent_run",
            "run_test",
        ),
        (
            ApprovalStatusChanged(
                approval_id="approval_test",
                company_id="cmp_test",
                from_status=ApprovalStatus.PENDING,
                to_status=ApprovalStatus.APPROVED,
            ),
            EventTypes.APPROVAL_GRANTED,
            "approval",
            "approval_test",
        ),
        (
            DecisionStatusChanged(
                decision_id="decision_test",
                company_id="cmp_test",
                from_status=DecisionStatus.PROPOSED,
                to_status=DecisionStatus.ACCEPTED,
            ),
            EventTypes.DECISION_UPDATED,
            "decision",
            "decision_test",
        ),
        (
            EvolutionRolloutStatusChanged(
                proposal_id="proposal_test",
                company_id="cmp_test",
                from_state=EvolutionRolloutState.PROPOSED,
                to_state=EvolutionRolloutState.SHADOW,
            ),
            EventTypes.EVOLUTION_PROPOSAL_UPDATED,
            "evolution_proposal",
            "proposal_test",
        ),
        (
            GoalStatusChanged(
                goal_id="goal_test",
                company_id="cmp_test",
                from_status=GoalStatus.ACTIVE,
                to_status=GoalStatus.COMPLETED,
            ),
            EventTypes.GOAL_UPDATED,
            "goal",
            "goal_test",
        ),
        (
            WorkItemStatusChanged(
                work_item_id="work_test",
                company_id="cmp_test",
                from_status=WorkItemStatus.QUEUED,
                to_status=WorkItemStatus.RUNNING,
            ),
            EventTypes.WORK_ITEM_UPDATED,
            "work_item",
            "work_test",
        ),
    ],
)
def test_domain_event_builds_audit_event(
    event,
    action: str,
    target_type: str,
    target_id: str,
) -> None:
    audit = audit_event_from_domain_event(
        event,
        DomainEventAuditContext(
            actor_type="user",
            actor_id="human:operator",
            trace_id="trace_test",
            run_id="run_context",
            work_item_id="work_context",
            detail={
                "source": "domain_event_collector",
                "context_statuses": (AgentRunStatus.RUNNING,),
            },
        ),
    )

    assert audit.company_id == "cmp_test"
    assert audit.action == action
    assert audit.target_type == target_type
    assert audit.target_id == target_id
    assert audit.actor_type == "user"
    assert audit.actor_id == "human:operator"
    assert audit.trace_id == "trace_test"
    assert audit.run_id == "run_context"
    assert audit.work_item_id == "work_context"
    assert audit.detail["company_id"] == "cmp_test"
    assert audit.detail["domain_event"] == type(event).__name__
    assert audit.detail["source"] == "domain_event_collector"
    assert audit.detail["context_statuses"] == ["running"]


class _RecordingAuditStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_append_domain_event_audits_uses_store_boundary() -> None:
    store = _RecordingAuditStore()
    event = GoalStatusChanged(
        goal_id="goal_test",
        company_id="cmp_test",
        from_status=GoalStatus.DRAFT,
        to_status=GoalStatus.ACTIVE,
    )

    appended = await append_control_plane_domain_event_audits(
        store,
        [event],
        DomainEventAuditContext(actor_id="system:test"),
    )

    assert appended == store.events
    assert store.events[0].action == EventTypes.GOAL_UPDATED
    assert store.events[0].detail["from_status"] == GoalStatus.DRAFT.value
    assert store.events[0].detail["to_status"] == GoalStatus.ACTIVE.value


def test_prompt_config_event_metadata_keys_normalize_to_json_list() -> None:
    event = AgentPromptConfigUpdated(
        company_id="cmp_test",
        agent_id="requirement-manager",
        prompt_length=42,
        metadata_keys=("source",),
    )

    audit = audit_event_from_domain_event(event, DomainEventAuditContext())

    assert audit.detail["metadata_keys"] == ["source"]
