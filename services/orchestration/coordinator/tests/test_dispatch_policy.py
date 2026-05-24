"""Tests for Coordinator dispatch-domain policy."""

from __future__ import annotations

from types import SimpleNamespace

from services.orchestration.coordinator.core.domain.dispatch import (
    CoordinatorDispatchPolicy,
    CoordinatorDispatchRoute,
    CoordinatorDispatchTarget,
    CoordinatorTargetRelationship,
)
from shared.schemas.event import EventTypes


def _decision(**overrides):
    base = {
        "target_agent": "requirement-manager",
        "action": "dispatch_task",
        "task_id": "task_1",
        "instruction": "Dispatch work",
        "workflow_id": "wf_1",
        "context": {},
        "command_id": None,
        "status": None,
        "summary": None,
        "scratchpad_ref": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_dispatch_route_classifies_known_and_unknown_targets() -> None:
    """Target classification is explicit and preserves generic passthrough."""
    dev_route = CoordinatorDispatchRoute.from_target_agent("dev-agent")
    unknown_route = CoordinatorDispatchRoute.from_target_agent("custom-agent")

    assert dev_route.target == CoordinatorDispatchTarget.DEV_AGENT
    assert dev_route.relationship == CoordinatorTargetRelationship.CUSTOMER_SUPPLIER
    assert dev_route.uses_specialized_contract is True

    assert unknown_route.target is None
    assert unknown_route.relationship == CoordinatorTargetRelationship.OPEN_HOST_SERVICE
    assert unknown_route.target_agent == "custom-agent"
    assert unknown_route.uses_specialized_contract is False


def test_dispatch_policy_maps_dev_contract() -> None:
    """Dev decisions use the typed PM-to-Dev event contract."""
    envelope = CoordinatorDispatchPolicy().envelope_for(
        _decision(
            target_agent="dev-agent",
            context={"wp_id": 42, "tasks": [{"title": "Implement"}]},
        )
    )

    assert envelope.event_type == EventTypes.PM_TASKS_READY_FOR_DEV
    assert envelope.payload["wp_id"] == 42
    assert envelope.payload["tasks"][0]["title"] == "Implement"
    assert envelope.route.target == CoordinatorDispatchTarget.DEV_AGENT


def test_dispatch_policy_maps_qa_contract() -> None:
    """QA decisions use the QA acceptance-request event contract."""
    envelope = CoordinatorDispatchPolicy().envelope_for(
        _decision(
            target_agent="qa-agent",
            context={
                "agent_name": "dev-agent",
                "commit_sha": "abc123",
                "mr_iid": 7,
                "gitlab_project_id": 1,
                "files_changed": ["a.py"],
            },
        )
    )

    assert envelope.event_type == EventTypes.QA_RUN_REQUESTED
    assert envelope.payload["requested_by"] == "coordinator"
    assert envelope.payload["files_changed"] == ["a.py"]
    assert envelope.route.target == CoordinatorDispatchTarget.QA_AGENT


def test_dispatch_policy_maps_chat_response_contract() -> None:
    """Chat decisions use the coordinator-response event contract."""
    envelope = CoordinatorDispatchPolicy().envelope_for(
        _decision(
            target_agent="chat-agent",
            command_id="cmd_1",
            status="completed",
            summary="Done",
        )
    )

    assert envelope.event_type == EventTypes.COORDINATOR_RESPONSE
    assert envelope.payload["command_id"] == "cmd_1"
    assert envelope.payload["status"] == "completed"
    assert envelope.payload["summary"] == "Done"
    assert envelope.route.target == CoordinatorDispatchTarget.CHAT_AGENT


def test_dispatch_policy_keeps_generic_dispatch_contract() -> None:
    """Requirement, PJM, and unknown targets use the generic dispatch envelope."""
    envelope = CoordinatorDispatchPolicy().envelope_for(
        _decision(
            target_agent="pjm-agent",
            scratchpad_ref="scratchpad/workflows/wf_1.md",
        )
    )

    assert envelope.event_type == EventTypes.COORDINATOR_DISPATCH
    assert envelope.payload["target_agent"] == "pjm-agent"
    assert envelope.payload["scratchpad_ref"] == "scratchpad/workflows/wf_1.md"
    assert envelope.route.target == CoordinatorDispatchTarget.PJM_AGENT
