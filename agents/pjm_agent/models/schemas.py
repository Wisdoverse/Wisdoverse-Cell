"""WBS (Work Breakdown Structure) Pydantic models for task decomposition.

Also contains event payload schemas for validated event handling.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class WBSTask(BaseModel):
    subject: str
    estimated_hours: int = Field(ge=1, le=16)


class WBSSubtask(BaseModel):
    subject: str
    estimated_days: int = Field(ge=1, le=5)
    priority: Literal["high", "medium", "low"] = "medium"
    depends_on: list[str] = []
    children: list[WBSTask] = Field(min_length=1, max_length=10)


class WBSResult(BaseModel):
    summary: str
    subtasks: list[WBSSubtask] = Field(min_length=1, max_length=8)


class TaskCheckResult(BaseModel):
    detailed: bool
    reason: str
    subtasks: list[WBSTask] = Field(default_factory=list)


# ============ Event Payload Schemas ============


class RiskDetectedPayload(BaseModel):
    """Payload for analysis.risk-detected events."""

    risks: list[dict[str, Any]] = []


class ChatPMQueryPayload(BaseModel):
    """Payload for chat.pm-query events."""

    user_id: str = ""


class DecomposePayload(BaseModel):
    """Payload for sync.task-needs-decompose events."""

    wp_id: int
    project_id: int
    subject: str = ""
    description: str = ""
    wp_type: str = "Feature"
    project_name: str = ""
    assignee: str = ""
    assignee_id: Optional[int] = None
