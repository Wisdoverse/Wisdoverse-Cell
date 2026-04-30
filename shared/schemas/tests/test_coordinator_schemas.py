"""Tests for coordinator payload models."""
import pytest
from pydantic import ValidationError


def test_task_usage_defaults():
    from shared.schemas.coordinator import TaskUsage
    usage = TaskUsage(duration_ms=1500)
    assert usage.duration_ms == 1500
    assert usage.llm_tokens == 0
    assert usage.tool_calls == 0


def test_task_notification_required_fields():
    from shared.schemas.coordinator import TaskNotification
    notif = TaskNotification(
        task_id="task_001",
        agent_id="dev-agent",
        status="completed",
        summary="Task finished successfully",
    )
    assert notif.task_id == "task_001"
    assert notif.result is None
    assert notif.usage is None
    assert notif.error is None


def test_task_notification_rejects_invalid_status():
    from shared.schemas.coordinator import TaskNotification
    with pytest.raises(ValidationError):
        TaskNotification(
            task_id="t1",
            agent_id="a1",
            status="running",
            summary="bad",
        )


def test_coordinator_command_required_fields():
    from shared.schemas.coordinator import CoordinatorCommand
    cmd = CoordinatorCommand(
        command_id="cmd_001",
        intent="create new feature",
        original_message="我们需要新功能",
        user_id="user_123",
        user_name="Alice",
    )
    assert cmd.priority == "normal"
    assert cmd.context == {}


def test_coordinator_response_required_fields():
    from shared.schemas.coordinator import CoordinatorResponse
    resp = CoordinatorResponse(
        command_id="cmd_001",
        status="completed",
        summary="Feature created",
    )
    assert resp.details == {}
    assert resp.follow_up is None


def test_agent_progress_required_fields():
    from shared.schemas.coordinator import AgentProgress, ToolActivity
    activity = ToolActivity(tool_name="llm_call", description="Analyzing PRD")
    progress = AgentProgress(
        task_id="task_001",
        agent_id="dev-agent",
        tool_use_count=5,
        llm_token_count=1200,
        last_activity=activity,
    )
    assert progress.recent_activities == []
    assert activity.is_read is False
    assert activity.is_write is False


def test_dispatch_permissions_defaults():
    from shared.schemas.coordinator import DispatchPermissions
    perms = DispatchPermissions()
    assert perms.allowed_tools is None
    assert perms.denied_tools == []
    assert perms.human_approval_required is False
    assert perms.max_llm_tokens is None


def test_dispatch_permissions_with_restrictions():
    from shared.schemas.coordinator import DispatchPermissions
    perms = DispatchPermissions(
        allowed_tools=["git_commit", "file_read"],
        denied_tools=["file_delete"],
        max_llm_tokens=50000,
        human_approval_required=True,
    )
    assert len(perms.allowed_tools) == 2
    assert perms.max_llm_tokens == 50000


def test_tool_activity_model_dump():
    from shared.schemas.coordinator import ToolActivity
    activity = ToolActivity(
        tool_name="feishu_api",
        description="Sending message",
        is_write=True,
    )
    data = activity.model_dump()
    assert data["tool_name"] == "feishu_api"
    assert data["is_write"] is True
