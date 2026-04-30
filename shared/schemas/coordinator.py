"""Coordinator Agent payload schemas.

Models for communication between Coordinator and other agents:
- TaskNotification: Agent → Coordinator completion report
- CoordinatorCommand: chat_agent → Coordinator escalation
- CoordinatorResponse: Coordinator → chat_agent result
- AgentProgress: Agent → Coordinator real-time progress
- DispatchPermissions: Coordinator → Agent capability limits
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TaskUsage(BaseModel):
    """Resource usage for a completed task."""
    model_config = ConfigDict(strict=True)

    duration_ms: int
    llm_tokens: int = 0
    tool_calls: int = 0


class TaskNotification(BaseModel):
    """Agent → Coordinator task completion notification."""
    model_config = ConfigDict(strict=True)

    task_id: str
    agent_id: str
    status: Literal["completed", "failed", "blocked"]
    summary: str
    result: dict[str, Any] | None = None
    usage: TaskUsage | None = None
    error: str | None = None


class CoordinatorCommand(BaseModel):
    """chat_agent → Coordinator escalation command."""
    command_id: str
    intent: str
    original_message: str
    user_id: str
    user_name: str
    context: dict[str, Any] = {}
    priority: Literal["normal", "high", "urgent"] = "normal"


class CoordinatorResponse(BaseModel):
    """Coordinator → chat_agent result."""
    command_id: str
    status: Literal["completed", "in_progress", "failed"]
    summary: str
    details: dict[str, Any] = {}
    follow_up: str | None = None


class ToolActivity(BaseModel):
    """Single tool invocation record for progress tracking."""
    tool_name: str
    description: str | None = None
    is_read: bool = False
    is_write: bool = False


class AgentProgress(BaseModel):
    """Agent → Coordinator real-time progress report."""
    task_id: str
    agent_id: str
    tool_use_count: int
    llm_token_count: int
    last_activity: ToolActivity | None = None
    recent_activities: list[ToolActivity] = []


class DispatchPermissions(BaseModel):
    """Coordinator → Agent capability limits per task dispatch."""
    allowed_tools: list[str] | None = None
    denied_tools: list[str] = []
    allowed_events: list[str] | None = None
    max_llm_tokens: int | None = None
    max_duration_ms: int | None = None
    human_approval_required: bool = False
