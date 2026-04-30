"""Tests for Coordinator decision-to-event dispatcher."""
from shared.schemas.event import EventTypes


def test_dispatch_to_requirement_manager():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="requirement-manager",
        action="dispatch_task",
        task_id="task_001",
        instruction="Produce PRD for @mention feature",
        workflow_id="wf_001",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_DISPATCH
    assert event.payload["target_agent"] == "requirement-manager"
    assert event.payload["instruction"] == "Produce PRD for @mention feature"
    assert event.source_agent == "coordinator"


def test_dispatch_to_dev_agent_preserves_contract():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="dev-agent",
        action="dispatch_task",
        task_id="task_002",
        instruction="Implement @mention parsing",
        workflow_id="wf_001",
        context={"wp_id": 100, "tasks": [{"id": 1, "title": "Parse mentions"}]},
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV
    assert event.payload["wp_id"] == 100
    assert event.payload["tasks"][0]["title"] == "Parse mentions"
    assert event.payload["instruction"] == "Implement @mention parsing"


def test_dispatch_to_qa_agent_preserves_contract():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="qa-agent",
        action="dispatch_task",
        task_id="task_003",
        instruction="Verify @mention feature",
        workflow_id="wf_001",
        context={
            "agent_name": "dev-agent",
            "commit_sha": "abc1234",
            "mr_iid": 42,
            "gitlab_project_id": 1,
            "files_changed": ["shared/integrations/feishu/mention.py"],
        },
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.QA_RUN_REQUESTED
    assert event.payload["agent_name"] == "dev-agent"
    assert event.payload["commit_sha"] == "abc1234"
    assert event.payload["requested_by"] == "coordinator"
    assert event.payload["instruction"] == "Verify @mention feature"


def test_dispatch_to_chat_agent_response():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="chat-agent",
        action="respond",
        task_id="task_004",
        instruction="",
        command_id="cmd_001",
        status="completed",
        summary="Feature shipped",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_RESPONSE
    assert event.payload["command_id"] == "cmd_001"
    assert event.payload["summary"] == "Feature shipped"


def test_dispatch_to_pjm_group():
    from agents.coordinator.core.dispatcher import decision_to_event
    from agents.coordinator.core.models import Decision
    decision = Decision(
        target_agent="pjm-agent",
        action="dispatch_task",
        task_id="task_005",
        instruction="Decompose PRD into tasks",
        workflow_id="wf_001",
        scratchpad_ref="scratchpad/workflows/wf_001.md",
    )
    event = decision_to_event(decision)
    assert event.event_type == EventTypes.COORDINATOR_DISPATCH
    assert event.payload["scratchpad_ref"] == "scratchpad/workflows/wf_001.md"
