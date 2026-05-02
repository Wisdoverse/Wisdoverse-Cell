"""
Tests for dev_agent event types and payload models.

Covers:
- EventTypes constants exist with correct values
- Payload model construction with valid data
- Payload model validation rejects invalid data
- All 6 event types registered in EVENT_PAYLOAD_MODELS
"""
import pytest
from pydantic import ValidationError

from shared.schemas.event import EventTypes
from shared.schemas.event_payloads import (
    EVENT_PAYLOAD_MODELS,
    AgentRunLifecyclePayload,
    AgentWakeupCompletedPayload,
    AgentWakeupRequestedPayload,
    ApprovalEventPayload,
    ArtifactEventPayload,
    AuditEventRecordedPayload,
    BudgetUsageRecordedPayload,
    DecisionEventPayload,
    DevMRCreatedPayload,
    DevTaskCompletedPayload,
    DevTaskFailedPayload,
    DevTaskInfo,
    DevWorkflowCompletedPayload,
    DevWorkflowCreatedPayload,
    GoalEventPayload,
    PMTasksReadyForDevPayload,
    WorkItemEventPayload,
    validate_event_payload,
)

# ============ EventTypes constants ============

class TestEventTypes:
    def test_pm_tasks_ready_for_dev(self):
        assert EventTypes.PM_TASKS_READY_FOR_DEV == "pm.tasks-ready-for-dev"

    def test_dev_workflow_created(self):
        assert EventTypes.DEV_WORKFLOW_CREATED == "dev.workflow-created"

    def test_dev_workflow_completed(self):
        assert EventTypes.DEV_WORKFLOW_COMPLETED == "dev.workflow-completed"

    def test_dev_mr_created(self):
        assert EventTypes.DEV_MR_CREATED == "dev.mr-created"

    def test_dev_task_completed(self):
        assert EventTypes.DEV_TASK_COMPLETED == "dev.task-completed"

    def test_dev_task_failed(self):
        assert EventTypes.DEV_TASK_FAILED == "dev.task-failed"

    def test_control_plane_agent_wakeup(self):
        assert EventTypes.AGENT_WAKEUP_REQUESTED == "agent.wakeup-requested"
        assert EventTypes.AGENT_WAKEUP_COMPLETED == "agent.wakeup-completed"

    def test_control_plane_agent_run(self):
        assert EventTypes.AGENT_RUN_STARTED == "agent_run.started"
        assert EventTypes.AGENT_RUN_SUCCEEDED == "agent_run.succeeded"
        assert EventTypes.AGENT_RUN_FAILED == "agent_run.failed"

    def test_control_plane_goal_and_work_item(self):
        assert EventTypes.GOAL_CREATED == "goal.created"
        assert EventTypes.GOAL_UPDATED == "goal.updated"
        assert EventTypes.WORK_ITEM_CREATED == "work_item.created"
        assert EventTypes.WORK_ITEM_UPDATED == "work_item.updated"

    def test_control_plane_decision_and_artifact(self):
        assert EventTypes.DECISION_CREATED == "decision.created"
        assert EventTypes.DECISION_UPDATED == "decision.updated"
        assert EventTypes.ARTIFACT_CREATED == "artifact.created"

    def test_control_plane_approval_budget_and_audit(self):
        assert EventTypes.APPROVAL_REQUESTED == "approval.requested"
        assert EventTypes.APPROVAL_GRANTED == "approval.granted"
        assert EventTypes.APPROVAL_REJECTED == "approval.rejected"
        assert EventTypes.BUDGET_USAGE_RECORDED == "budget.usage-recorded"
        assert EventTypes.AUDIT_EVENT_RECORDED == "audit.event-recorded"


# ============ DevTaskInfo ============

class TestDevTaskInfo:
    def test_construction(self):
        info = DevTaskInfo(id=1, title="Build API")
        assert info.id == 1
        assert info.title == "Build API"
        assert info.description == ""
        assert info.estimated_hours == 8

    def test_with_optional_fields(self):
        info = DevTaskInfo(
            id=2, title="Write tests", description="Add unit tests",
            estimated_hours=4.0, parent_story="US-1",
            related_files=["agents/gateways/user_interaction/"],
        )
        assert info.estimated_hours == 4.0
        assert info.parent_story == "US-1"
        assert info.related_files == ["agents/gateways/user_interaction/"]

    def test_negative_estimated_hours_rejected(self):
        with pytest.raises(ValidationError):
            DevTaskInfo(id=1, title="X", estimated_hours=-1)

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            DevTaskInfo(title="no id")  # type: ignore[call-arg]


# ============ PMTasksReadyForDevPayload ============

class TestPMTasksReadyForDevPayload:
    def test_construction(self):
        payload = PMTasksReadyForDevPayload(
            wp_id=42,
            tasks=[DevTaskInfo(id=1, title="Do thing")],
        )
        assert payload.wp_id == 42
        assert len(payload.tasks) == 1

    def test_empty_tasks_rejected(self):
        with pytest.raises(ValidationError):
            PMTasksReadyForDevPayload(wp_id=1, tasks=[])

    def test_missing_wp_id(self):
        with pytest.raises(ValidationError):
            PMTasksReadyForDevPayload(tasks=[DevTaskInfo(id=1, title="X")])  # type: ignore[call-arg]


# ============ DevWorkflowCreatedPayload ============

class TestDevWorkflowCreatedPayload:
    def test_construction(self):
        payload = DevWorkflowCreatedPayload(
            task_id="t-1", workflow_id="wf-abc", node_count=5
        )
        assert payload.task_id == "t-1"
        assert payload.workflow_id == "wf-abc"
        assert payload.node_count == 5

    def test_zero_node_count_rejected(self):
        with pytest.raises(ValidationError):
            DevWorkflowCreatedPayload(
                task_id="t-1", workflow_id="wf-abc", node_count=0
            )


# ============ DevWorkflowCompletedPayload ============

class TestDevWorkflowCompletedPayload:
    def test_construction(self):
        payload = DevWorkflowCompletedPayload(
            task_id="t-1", workflow_id="wf-abc", duration_s=12.5
        )
        assert payload.duration_s == 12.5

    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            DevWorkflowCompletedPayload(
                task_id="t-1", workflow_id="wf-abc", duration_s=-1
            )


# ============ DevMRCreatedPayload ============

class TestDevMRCreatedPayload:
    def test_construction(self):
        payload = DevMRCreatedPayload(
            mr_url="https://gitlab.com/mr/1",
            wp_id=42,
            branch="feat/dev-agent",
        )
        assert payload.mr_url == "https://gitlab.com/mr/1"
        assert payload.risk_level == "MEDIUM"  # default

    def test_risk_level_values(self):
        for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            payload = DevMRCreatedPayload(
                mr_url="https://x", wp_id=1, branch="b", risk_level=level
            )
            assert payload.risk_level == level

    def test_invalid_risk_level_rejected(self):
        with pytest.raises(ValidationError):
            DevMRCreatedPayload(
                mr_url="https://x", wp_id=1, branch="b", risk_level="unknown"
            )


# ============ DevTaskCompletedPayload ============

class TestDevTaskCompletedPayload:
    def test_construction(self):
        payload = DevTaskCompletedPayload(
            wp_id=42, mr_url="https://gitlab.com/mr/1", duration_s=60.0
        )
        assert payload.wp_id == 42
        assert payload.duration_s == 60.0

    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            DevTaskCompletedPayload(wp_id=1, mr_url="x", duration_s=-5)


# ============ DevTaskFailedPayload ============

class TestDevTaskFailedPayload:
    def test_construction(self):
        payload = DevTaskFailedPayload(wp_id=42, error="lint failed")
        assert payload.wp_id == 42
        assert payload.error == "lint failed"
        assert payload.failed_node is None
        assert payload.runbook_url is None

    def test_with_optional_fields(self):
        payload = DevTaskFailedPayload(
            wp_id=42,
            error="test failed",
            failed_node="run_tests",
            runbook_url="https://wiki/runbook",
        )
        assert payload.failed_node == "run_tests"
        assert payload.runbook_url == "https://wiki/runbook"

    def test_missing_error_rejected(self):
        with pytest.raises(ValidationError):
            DevTaskFailedPayload(wp_id=42)  # type: ignore[call-arg]


# ============ EVENT_PAYLOAD_MODELS registration ============

class TestEventPayloadModelsRegistration:
    @pytest.mark.parametrize(
        "event_type,model_cls",
        [
            ("pm.tasks-ready-for-dev", PMTasksReadyForDevPayload),
            ("dev.workflow-created", DevWorkflowCreatedPayload),
            ("dev.workflow-completed", DevWorkflowCompletedPayload),
            ("dev.mr-created", DevMRCreatedPayload),
            ("dev.task-completed", DevTaskCompletedPayload),
            ("dev.task-failed", DevTaskFailedPayload),
            ("goal.created", GoalEventPayload),
            ("goal.updated", GoalEventPayload),
            ("work_item.created", WorkItemEventPayload),
            ("work_item.updated", WorkItemEventPayload),
            ("decision.created", DecisionEventPayload),
            ("decision.updated", DecisionEventPayload),
            ("artifact.created", ArtifactEventPayload),
            ("agent.wakeup-requested", AgentWakeupRequestedPayload),
            ("agent.wakeup-completed", AgentWakeupCompletedPayload),
            ("agent_run.started", AgentRunLifecyclePayload),
            ("agent_run.succeeded", AgentRunLifecyclePayload),
            ("agent_run.failed", AgentRunLifecyclePayload),
            ("approval.requested", ApprovalEventPayload),
            ("approval.granted", ApprovalEventPayload),
            ("approval.rejected", ApprovalEventPayload),
            ("budget.usage-recorded", BudgetUsageRecordedPayload),
            ("audit.event-recorded", AuditEventRecordedPayload),
        ],
    )
    def test_registered(self, event_type, model_cls):
        assert EVENT_PAYLOAD_MODELS[event_type] is model_cls

    def test_validate_control_plane_wakeup_payload(self):
        result = validate_event_payload(
            "agent.wakeup-requested",
            {
                "company_id": "cmp_test",
                "agent_id": "ops-runner",
                "actor_id": "human:board",
                "input": {"task": "check"},
            },
        )
        assert isinstance(result, AgentWakeupRequestedPayload)

    def test_validate_control_plane_goal_payload(self):
        result = validate_event_payload(
            "goal.created",
            {
                "company_id": "cmp_test",
                "goal_id": "goal_001",
                "title": "Ship control plane",
                "status": "active",
            },
        )
        assert isinstance(result, GoalEventPayload)

    def test_validate_control_plane_work_item_payload(self):
        result = validate_event_payload(
            "work_item.created",
            {
                "company_id": "cmp_test",
                "goal_id": "goal_001",
                "work_item_id": "work_001",
                "title": "Expose API",
                "status": "ready",
                "priority": "high",
            },
        )
        assert isinstance(result, WorkItemEventPayload)

    def test_validate_control_plane_decision_payload(self):
        result = validate_event_payload(
            "decision.created",
            {
                "company_id": "cmp_test",
                "decision_id": "dec_001",
                "title": "Accept output",
                "status": "accepted",
                "run_id": "run_001",
            },
        )
        assert isinstance(result, DecisionEventPayload)

    def test_validate_control_plane_artifact_payload(self):
        result = validate_event_payload(
            "artifact.created",
            {
                "company_id": "cmp_test",
                "artifact_id": "art_001",
                "artifact_type": "run_walkthrough",
                "title": "Run walkthrough",
                "uri": "artifact://run",
                "run_id": "run_001",
            },
        )
        assert isinstance(result, ArtifactEventPayload)

    def test_validate_control_plane_approval_payload(self):
        result = validate_event_payload(
            "approval.requested",
            {
                "company_id": "cmp_test",
                "approval_id": "apr_001",
                "category": "technical",
                "status": "pending",
                "requested_by": "agent:dev-agent",
                "source_agent_id": "dev-agent",
                "proposed_action": "Run workflow",
                "risk": "External system mutation",
                "trace_id": "trace_approval",
            },
        )
        assert isinstance(result, ApprovalEventPayload)

    def test_validate_control_plane_budget_payload(self):
        result = validate_event_payload(
            "budget.usage-recorded",
            {
                "company_id": "cmp_test",
                "usage_id": "busg_001",
                "budget_id": "bud_001",
                "scope": "agent",
                "scope_id": "dev-agent",
                "period": "daily",
                "cost_usd": 0.42,
                "model": "tool:agentforge_run",
                "run_id": "run_001",
                "trace_id": "trace_budget",
            },
        )
        assert isinstance(result, BudgetUsageRecordedPayload)

    def test_validate_control_plane_audit_payload(self):
        result = validate_event_payload(
            "audit.event-recorded",
            {
                "company_id": "cmp_test",
                "audit_event_id": "aud_001",
                "action": "agent_run.started",
                "target_type": "agent_run",
                "target_id": "run_001",
                "actor_type": "agent",
                "actor_id": "dev-agent",
                "run_id": "run_001",
                "trace_id": "trace_audit",
                "idempotency_key": "agent_run.started:run_001",
            },
        )
        assert isinstance(result, AuditEventRecordedPayload)

    def test_validate_event_payload_happy_path(self):
        result = validate_event_payload(
            "dev.task-failed",
            {"wp_id": 1, "error": "boom"},
        )
        assert isinstance(result, DevTaskFailedPayload)

    def test_validate_event_payload_invalid(self):
        with pytest.raises(ValidationError):
            validate_event_payload("dev.task-failed", {"wp_id": 1})  # missing error
