"""Internal models for Coordinator decision-making."""
from typing import Any

from pydantic import BaseModel


class Decision(BaseModel):
    """A single decision from the Coordinator's _think() step."""

    target_agent: str
    action: str
    task_id: str
    instruction: str
    workflow_id: str | None = None
    priority: str = "normal"
    reasoning: str = ""
    context: dict[str, Any] = {}
    command_id: str | None = None
    status: str | None = None
    summary: str | None = None
    scratchpad_ref: str | None = None
    permissions: Any | None = None
