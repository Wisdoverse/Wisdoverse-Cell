"""Tests for Control Plane domain-event base semantics."""

from __future__ import annotations

import pytest

from shared.control_plane.domain import ControlPlaneDomainEvent
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
from shared.control_plane.models import (
    AgentRunStatus,
    ApprovalStatus,
    DecisionStatus,
    EvolutionRolloutState,
    GoalStatus,
    WorkItemStatus,
)


@pytest.mark.parametrize(
    "event",
    [
        ArtifactCreated(
            artifact_id="artifact_1",
            company_id="cmp_test",
            artifact_type="report",
            goal_id=None,
            work_item_id=None,
            run_id=None,
            created_by_agent_id=None,
            has_content_hash=False,
        ),
        BudgetPolicyCreated(
            budget_id="budget_1",
            company_id="cmp_test",
            scope="agent",
            scope_id="dev-agent",
            period="daily",
            limit_usd=20,
            warning_threshold=0.8,
            status=BudgetPolicyStatus.ACTIVE,
            model_allowlist=("gpt-5",),
        ),
        BudgetPolicyUpdated(
            budget_id="budget_1",
            company_id="cmp_test",
            scope="agent",
            scope_id="dev-agent",
            period="daily",
            from_status=BudgetPolicyStatus.ACTIVE,
            to_status=BudgetPolicyStatus.PAUSED,
            changed_fields=("status",),
        ),
        BudgetUsageRecorded(
            usage_id="usage_1",
            company_id="cmp_test",
            budget_id="budget_1",
            cost_usd=0.42,
            model="tool:agentforge_apply",
            input_tokens=10,
            output_tokens=5,
            run_id="run_1",
            trace_id="trace_1",
            metadata_keys=("tool",),
        ),
        CompanyContextCreated(
            company_id="cmp_test",
            name_length=10,
            mission_length=20,
            metadata_keys=("stage",),
        ),
        CompanyContextUpdated(
            company_id="cmp_test",
            name_changed=True,
            mission_changed=False,
            metadata_changed=True,
            name_length=10,
            mission_length=20,
            metadata_keys=("stage",),
        ),
        AgentPromptConfigUpdated(
            company_id="cmp_test",
            agent_id="requirement-manager",
            prompt_length=42,
            metadata_keys=("source",),
        ),
        AgentRoleStatusChanged(
            role_id="role_1",
            agent_id="ops-runner",
            company_id="cmp_test",
            from_status=AgentRoleStatus.ACTIVE,
            to_status=AgentRoleStatus.PAUSED,
        ),
        AgentRunStatusChanged(
            run_id="run_1",
            agent_id="dev-agent",
            company_id="cmp_test",
            from_status=AgentRunStatus.PENDING,
            to_status=AgentRunStatus.RUNNING,
        ),
        ApprovalStatusChanged(
            approval_id="appr_1",
            company_id="cmp_test",
            from_status=ApprovalStatus.PENDING,
            to_status=ApprovalStatus.APPROVED,
        ),
        DecisionStatusChanged(
            decision_id="dec_1",
            company_id="cmp_test",
            from_status=DecisionStatus.PROPOSED,
            to_status=DecisionStatus.ACCEPTED,
        ),
        EvolutionRolloutStatusChanged(
            proposal_id="evo_1",
            company_id="cmp_test",
            from_state=EvolutionRolloutState.PROPOSED,
            to_state=EvolutionRolloutState.CANARY,
        ),
        GoalStatusChanged(
            goal_id="goal_1",
            company_id="cmp_test",
            from_status=GoalStatus.DRAFT,
            to_status=GoalStatus.ACTIVE,
        ),
        WorkItemStatusChanged(
            work_item_id="work_1",
            company_id="cmp_test",
            from_status=WorkItemStatus.QUEUED,
            to_status=WorkItemStatus.RUNNING,
        ),
    ],
)
def test_control_plane_domain_events_share_base_type(
    event: ControlPlaneDomainEvent,
) -> None:
    assert isinstance(event, ControlPlaneDomainEvent)
    assert event.event_name == type(event).__name__
    assert event.to_payload()["company_id"] == "cmp_test"
