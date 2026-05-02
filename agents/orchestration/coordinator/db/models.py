"""Coordinator persistent state models."""
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowState(BaseModel):
    """Active workflow state."""
    workflow_id: str
    type: str
    status: Literal["active", "paused", "completed", "failed"]
    current_phase: str
    agents_involved: list[str]
    created_at: datetime
    updated_at: datetime
    context: dict[str, Any] = {}


class AgentStateRecord(BaseModel):
    """Agent runtime state as seen by Coordinator."""
    agent_id: str
    status: Literal["idle", "working", "blocked", "error"]
    current_task: str | None = None
    last_output_at: datetime | None = None
    error: str | None = None


class DecisionRecord(BaseModel):
    """Coordinator decision log entry."""
    decision_id: str
    workflow_id: str | None = None
    reasoning: str
    action: str
    target_agent: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    outcome: str | None = None
