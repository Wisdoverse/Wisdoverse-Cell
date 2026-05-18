"""Pydantic schemas for dev_agent."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.dev_agent.core.task_lifecycle import VALID_TRANSITIONS as VALID_TRANSITIONS


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WorkflowNode(BaseModel):
    """Single node in an AgentForge workflow."""

    model_config = ConfigDict(strict=True)
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["agent_task", "human_review"] = "agent_task"
    dependsOn: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class WorkflowPlan(BaseModel):
    """Complete AgentForge workflow definition."""

    model_config = ConfigDict(strict=True)
    name: str = Field(..., min_length=1)
    description: str = ""
    nodes: list[WorkflowNode] = Field(..., min_length=1)


class ToolRule(BaseModel):
    """Rule for assigning AI tool to a workflow node."""

    match_tags: list[str] = Field(..., min_length=1)
    tool: Literal["claude", "gemini", "codex"]
    priority: int = 0


class TaskInput(BaseModel):
    """Task input from PJM."""

    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=5000)
    estimated_hours: float = Field(ge=0, le=100)
    wp_id: int = 0
    parent_story: str = ""
    related_files: list[str] = Field(default_factory=list)


class SanitizedTask(TaskInput):
    """Task after passing InputSanitizer."""

    risk_level: RiskLevel = RiskLevel.MEDIUM
