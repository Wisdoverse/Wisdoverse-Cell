"""
Tests for dev_agent event types and payload models.

Covers:
- EventTypes constants exist with correct values
- Payload model construction with valid data
- Payload model validation rejects invalid data
- Runtime event types are registered in EVENT_PAYLOAD_MODELS
"""
import pytest
from pydantic import ValidationError

from shared.schemas.event import EventTypes
from shared.schemas.event_payloads import (
    EVENT_PAYLOAD_MODELS,
    A2ATaskErrorPayload,
    A2ATaskEventPayload,
    AgentProgress,
    AgentRoleCreatedPayload,
    AgentRoleStatusUpdatedPayload,
    AgentRunLifecyclePayload,
    AgentWakeupCompletedPayload,
    AgentWakeupRequestedPayload,
    ApprovalEventPayload,
    ArtifactEventPayload,
    AuditEventRecordedPayload,
    BudgetUsageRecordedPayload,
    CompanyEventPayload,
    CoordinatorCommand,
    CoordinatorDispatchPayload,
    CoordinatorResponse,
    DecisionEventPayload,
    DevMRCreatedPayload,
    DevTaskCompletedPayload,
    DevTaskFailedPayload,
    DevTaskInfo,
    DevWorkflowCompletedPayload,
    DevWorkflowCreatedPayload,
    DLQFailedPayload,
    EvolutionCycleTriggeredPayload,
    EvolutionHumanFeedbackPayload,
    EvolutionPatternApprovedPayload,
    EvolutionPatternProposedPayload,
    EvolutionProposalEventPayload,
    EvolutionSkillProposedPayload,
    GoalEventPayload,
    MeetingUploadedPayload,
    PMApprovalTimeoutPayload,
    PMDecomposeCompletedPayload,
    PMDecompositionFailedPayload,
    PMPrdReadyPayload,
    PMTasksReadyForDevPayload,
    ProjectEventPayload,
    QualityEvaluatedPayload,
    RiskDetectedPayload,
    SprintCompletedPayload,
    SprintStartedPayload,
    SyncCompletedPayload,
    SyncFailedPayload,
    SyncStartedPayload,
    SyncTriggerPayload,
    TaskNotification,
    WorkItemEventPayload,
    validate_event_payload,
)

# ============ EventTypes constants ============

class TestEventTypes:
    def test_pm_tasks_ready_for_dev(self):
        assert EventTypes.PM_TASKS_READY_FOR_DEV == "pm.tasks-ready-for-dev"

    def test_pm_prd_ready(self):
        assert EventTypes.PM_PRD_READY == "pm.prd-ready"

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
        assert EventTypes.COMPANY_CREATED == "company.created"
        assert EventTypes.COMPANY_UPDATED == "company.updated"
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
        assert EventTypes.EVOLUTION_PROPOSAL_CREATED == "evolution_proposal.created"
        assert EventTypes.EVOLUTION_PROPOSAL_UPDATED == "evolution_proposal.updated"
        assert EventTypes.DLQ_FAILED == "dlq.failed"
        assert EventTypes.BUDGET_USAGE_RECORDED == "budget.usage-recorded"
        assert EventTypes.AUDIT_EVENT_RECORDED == "audit.event-recorded"

    def test_external_work_context_events(self):
        assert EventTypes.PROJECT_CREATED == "project.created"
        assert EventTypes.PROJECT_UPDATED == "project.updated"
        assert EventTypes.SPRINT_STARTED == "sprint.started"
        assert EventTypes.SPRINT_COMPLETED == "sprint.completed"
        assert EventTypes.MEETING_UPLOADED == "meeting.uploaded"

    def test_sync_events(self):
        assert EventTypes.SYNC_TRIGGER == "sync.trigger"
        assert EventTypes.SYNC_STARTED == "sync.started"
        assert EventTypes.SYNC_COMPLETED == "sync.completed"
        assert EventTypes.SYNC_FAILED == "sync.failed"

    def test_a2a_bridge_events(self):
        assert EventTypes.A2A_TASK_SUBMITTED == "a2a.task.submitted"
        assert EventTypes.A2A_TASK_WORKING == "a2a.task.working"
        assert EventTypes.A2A_TASK_INPUT_REQUIRED == "a2a.task.input-required"
        assert EventTypes.A2A_TASK_COMPLETED == "a2a.task.completed"
        assert EventTypes.A2A_TASK_FAILED == "a2a.task.failed"
        assert EventTypes.A2A_TASK_CANCELED == "a2a.task.canceled"
        assert EventTypes.A2A_TASK_ERROR == "a2a.task.error"


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
            related_files=["services/gateways/user_interaction/"],
        )
        assert info.estimated_hours == 4.0
        assert info.parent_story == "US-1"
        assert info.related_files == ["services/gateways/user_interaction/"]

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


# ============ PMPrdReadyPayload ============

class TestPMPrdReadyPayload:
    def test_construction(self):
        payload = PMPrdReadyPayload(
            requirement_id="req_001",
            prd_id="prd_001",
            title="Login PRD",
            prd_uri="https://docs.example/prd_001",
            summary="Ready for decomposition",
            workflow_id="wf_001",
        )
        assert payload.requirement_id == "req_001"
        assert payload.prd_id == "prd_001"


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
            ("company.created", CompanyEventPayload),
            ("company.updated", CompanyEventPayload),
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
            ("agent_role.created", AgentRoleCreatedPayload),
            ("agent_role.status-updated", AgentRoleStatusUpdatedPayload),
            ("approval.requested", ApprovalEventPayload),
            ("approval.granted", ApprovalEventPayload),
            ("approval.rejected", ApprovalEventPayload),
            ("budget.usage-recorded", BudgetUsageRecordedPayload),
            ("audit.event-recorded", AuditEventRecordedPayload),
            ("evolution_proposal.created", EvolutionProposalEventPayload),
            ("evolution_proposal.updated", EvolutionProposalEventPayload),
            ("evolution.cycle-triggered", EvolutionCycleTriggeredPayload),
            ("evolution.skill-proposed", EvolutionSkillProposedPayload),
            ("evolution.human-feedback", EvolutionHumanFeedbackPayload),
            ("evolution.pattern-proposed", EvolutionPatternProposedPayload),
            ("evolution.pattern-approved", EvolutionPatternApprovedPayload),
            ("dlq.failed", DLQFailedPayload),
            ("project.created", ProjectEventPayload),
            ("project.updated", ProjectEventPayload),
            ("sprint.started", SprintStartedPayload),
            ("sprint.completed", SprintCompletedPayload),
            ("meeting.uploaded", MeetingUploadedPayload),
            ("analysis.risk-detected", RiskDetectedPayload),
            ("analysis.quality-evaluated", QualityEvaluatedPayload),
            ("pm.decompose-completed", PMDecomposeCompletedPayload),
            ("pm.decomposition-failed", PMDecompositionFailedPayload),
            ("pm.approval-timeout", PMApprovalTimeoutPayload),
            ("pm.prd-ready", PMPrdReadyPayload),
            ("coordinator.command", CoordinatorCommand),
            ("coordinator.response", CoordinatorResponse),
            ("coordinator.dispatch", CoordinatorDispatchPayload),
            ("task.notification", TaskNotification),
            ("task.progress", AgentProgress),
            ("a2a.task.submitted", A2ATaskEventPayload),
            ("a2a.task.working", A2ATaskEventPayload),
            ("a2a.task.input-required", A2ATaskEventPayload),
            ("a2a.task.completed", A2ATaskEventPayload),
            ("a2a.task.failed", A2ATaskEventPayload),
            ("a2a.task.canceled", A2ATaskEventPayload),
            ("a2a.task.error", A2ATaskErrorPayload),
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

    def test_validate_control_plane_company_payload(self):
        result = validate_event_payload(
            "company.created",
            {
                "company_id": "cmp_test",
                "name": "Wisdoverse Cell",
                "mission": "Operate with agents",
            },
        )
        assert isinstance(result, CompanyEventPayload)

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

    def test_validate_control_plane_evolution_proposal_payload(self):
        result = validate_event_payload(
            "evolution_proposal.created",
            {
                "company_id": "cmp_test",
                "proposal_id": "evo_001",
                "tier": "L2",
                "scope": "agent-routing",
                "approval_state": "pending",
                "rollout_state": "proposed",
                "approval_id": "appr_001",
            },
        )
        assert isinstance(result, EvolutionProposalEventPayload)

    def test_validate_control_plane_agent_role_created_payload(self):
        result = validate_event_payload(
            "agent_role.created",
            {
                "company_id": "cmp_test",
                "agent_id": "requirement-manager",
                "role_id": "role_001",
                "agent_kind": "business_runtime",
                "interaction_mode": "routed",
                "role": "requirements",
                "adapter_type": "http",
            },
        )
        assert isinstance(result, AgentRoleCreatedPayload)

    def test_validate_control_plane_agent_role_status_payload(self):
        result = validate_event_payload(
            "agent_role.status-updated",
            {
                "company_id": "cmp_test",
                "agent_id": "requirement-manager",
                "status": "active",
                "actor_id": "human:operator",
            },
        )
        assert isinstance(result, AgentRoleStatusUpdatedPayload)

    def test_validate_dlq_failed_payload(self):
        result = validate_event_payload(
            "dlq.failed",
            {
                "original_event_id": "evt_001",
                "original_event_type": "work.execute",
                "original_source": "coordinator",
                "original_payload": {"work_item_id": "work_001"},
                "failed_by_agent": "dev-agent",
                "failure_stage": "handler",
                "error": "timeout",
            },
        )
        assert isinstance(result, DLQFailedPayload)

    def test_validate_meeting_uploaded_payload(self):
        result = validate_event_payload(
            "meeting.uploaded",
            {
                "content": "Discuss login requirements.",
                "source": "feishu",
                "title": "Planning",
                "participants": ["Alice"],
                "source_id": "meeting_001",
            },
        )
        assert isinstance(result, MeetingUploadedPayload)

    def test_validate_sprint_started_payload(self):
        result = validate_event_payload(
            "sprint.started",
            {
                "sprint_id": "spr_001",
                "name": "Sprint 1",
                "requirement_ids": ["req_1"],
                "start_date": "2026-05-03",
            },
        )
        assert isinstance(result, SprintStartedPayload)

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

    def test_validate_a2a_task_event_payload(self):
        result = validate_event_payload(
            "a2a.task.completed",
            {
                "task_id": "task_001",
                "context_id": "trace_001",
                "status": "completed",
                "message": "Done",
                "artifacts": [
                    {
                        "artifact_id": "art_001",
                        "name": "result.json",
                        "description": "Analysis result",
                    }
                ],
            },
        )
        assert isinstance(result, A2ATaskEventPayload)
        assert result.artifacts[0].name == "result.json"

    def test_validate_a2a_task_error_payload(self):
        result = validate_event_payload(
            "a2a.task.error",
            {
                "error": "routing failed",
                "original_event_type": "requirement.extracted",
            },
        )
        assert isinstance(result, A2ATaskErrorPayload)

    def test_validate_a2a_task_status_rejected(self):
        with pytest.raises(ValidationError):
            validate_event_payload(
                "a2a.task.completed",
                {
                    "task_id": "task_001",
                    "context_id": "trace_001",
                    "status": "unknown",
                },
            )


class TestSyncPayloadContracts:
    def test_validate_sync_trigger_payload(self):
        result = validate_event_payload(
            "sync.trigger",
            {"triggered_by": "chat_tool", "scope": "feishu-bitable"},
        )
        assert isinstance(result, SyncTriggerPayload)
        assert result.scope == "feishu-bitable"

    def test_validate_sync_started_payload(self):
        result = validate_event_payload(
            "sync.started",
            {"triggered_by": "scheduler", "scope": "openproject"},
        )
        assert isinstance(result, SyncStartedPayload)

    def test_validate_sync_completed_payload(self):
        result = validate_event_payload(
            "sync.completed",
            {"synced_count": 3, "scope": "feishu_bitable", "errors": []},
        )
        assert isinstance(result, SyncCompletedPayload)

    def test_validate_sync_failed_payload(self):
        result = validate_event_payload(
            "sync.failed",
            {"error": "upstream timeout", "scope": "openproject"},
        )
        assert isinstance(result, SyncFailedPayload)


class TestPMAndAnalysisPayloadContracts:
    def test_validate_quality_evaluated_payload(self):
        result = validate_event_payload(
            "analysis.quality-evaluated",
            {"evaluations": [{"task": "T1", "quality": "pass"}]},
        )
        assert isinstance(result, QualityEvaluatedPayload)

    def test_validate_pm_decomposition_failed_payload(self):
        result = validate_event_payload(
            "pm.decomposition-failed",
            {
                "error": "LLM timeout",
                "requirement_title": "Login flow",
                "trace_id": "trace_001",
            },
        )
        assert isinstance(result, PMDecompositionFailedPayload)

    def test_validate_pm_approval_timeout_payload(self):
        result = validate_event_payload(
            "pm.approval-timeout",
            {"record_id": "dec_001", "age_hours": 24.5},
        )
        assert isinstance(result, PMApprovalTimeoutPayload)

    def test_validate_pm_prd_ready_payload(self):
        result = validate_event_payload(
            "pm.prd-ready",
            {"requirement_id": "req_001", "title": "Login PRD"},
        )
        assert isinstance(result, PMPrdReadyPayload)


class TestEvolutionPayloadContracts:
    def test_validate_evolution_cycle_triggered_payload(self):
        result = validate_event_payload(
            "evolution.cycle-triggered",
            {"days": 14},
        )
        assert isinstance(result, EvolutionCycleTriggeredPayload)

    def test_validate_evolution_skill_proposed_payload(self):
        result = validate_event_payload(
            "evolution.skill-proposed",
            {
                "operation": "add_skill",
                "target_agent": "pjm-agent",
                "target_skill": "decompose",
                "confidence": 0.8,
                "control_plane_approval_id": "appr_001",
            },
        )
        assert isinstance(result, EvolutionSkillProposedPayload)

    def test_validate_evolution_human_feedback_payload(self):
        result = validate_event_payload(
            "evolution.human-feedback",
            {
                "approved": True,
                "control_plane_approval_id": "appr_001",
                "user_id": "human:operator",
            },
        )
        assert isinstance(result, EvolutionHumanFeedbackPayload)

    def test_validate_evolution_pattern_proposed_payload(self):
        result = validate_event_payload(
            "evolution.pattern-proposed",
            {
                "pattern_id": "pat_001",
                "name": "QA after dev",
                "trigger_event": "dev.mr-created",
                "steps": [{"agent_id": "qa-agent"}],
            },
        )
        assert isinstance(result, EvolutionPatternProposedPayload)

    def test_validate_evolution_pattern_approved_payload(self):
        result = validate_event_payload(
            "evolution.pattern-approved",
            {
                "pattern_id": "pat_001",
                "approved": True,
                "user_id": "human:operator",
            },
        )
        assert isinstance(result, EvolutionPatternApprovedPayload)


class TestCoordinatorPayloadContracts:
    def test_validate_coordinator_command_payload(self):
        result = validate_event_payload(
            "coordinator.command",
            {
                "command_id": "cmd_001",
                "intent": "decompose",
                "original_message": "Break this into tasks",
                "user_id": "ou_001",
                "user_name": "Operator",
            },
        )
        assert isinstance(result, CoordinatorCommand)

    def test_validate_coordinator_response_payload(self):
        result = validate_event_payload(
            "coordinator.response",
            {
                "command_id": "cmd_001",
                "status": "completed",
                "summary": "Done",
            },
        )
        assert isinstance(result, CoordinatorResponse)

    def test_validate_coordinator_dispatch_payload(self):
        result = validate_event_payload(
            "coordinator.dispatch",
            {
                "target_agent": "requirement-manager",
                "task_id": "task_001",
                "instruction": "Draft PRD",
                "workflow_id": "wf_001",
                "scratchpad_ref": "scratchpad/workflows/wf_001.md",
            },
        )
        assert isinstance(result, CoordinatorDispatchPayload)

    def test_validate_task_notification_payload(self):
        result = validate_event_payload(
            "task.notification",
            {
                "task_id": "task_001",
                "agent_id": "pjm-agent",
                "status": "completed",
                "summary": "Decomposed",
            },
        )
        assert isinstance(result, TaskNotification)

    def test_validate_task_progress_payload(self):
        result = validate_event_payload(
            "task.progress",
            {
                "task_id": "task_001",
                "agent_id": "dev-agent",
                "tool_use_count": 2,
                "llm_token_count": 300,
            },
        )
        assert isinstance(result, AgentProgress)
