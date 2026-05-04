"""
Collaboration pattern models for multi-agent coordination.

Defines the data structures for collaboration patterns that describe
how multiple agents coordinate to handle a specific trigger event.
Patterns go through a lifecycle: proposed -> shadow -> active -> retired.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.core.ids import generate_id


class PatternStatus(str, Enum):
    PROPOSED = "proposed"
    SHADOW = "shadow"
    ACTIVE = "active"
    RETIRED = "retired"


class CollaborationStep(BaseModel):
    """A single step in a multi-agent collaboration pattern."""

    step_id: str
    agent_id: str
    action: str  # "analyze" | "review" | "decide" | "notify"
    input_from: str | None = None
    output_to: str | None = None
    on_failure: str = "abort"  # "abort" | "skip" | "fallback_to:{step_id}"
    skill_id: str = ""
    timeout_seconds: int = 30


class CollaborationPattern(BaseModel):
    """
    A collaboration pattern defining how agents coordinate on a trigger event.

    Lifecycle: PROPOSED -> SHADOW (runs in background) -> ACTIVE -> RETIRED.
    """

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    pattern_id: str = Field(default_factory=lambda: generate_id("pat"))
    name: str
    status: PatternStatus = PatternStatus.PROPOSED
    trigger_event: str
    trigger_condition: str | None = None
    steps: list[CollaborationStep]
    shadow_results: list[dict[str, Any]] = Field(default_factory=list)
    production_results: list[dict[str, Any]] = Field(default_factory=list)
    human_approval: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ShadowRunResult(BaseModel):
    """Result of running a pattern in shadow mode alongside production."""

    pattern_id: str
    trigger_event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    steps: list[dict[str, Any]] = Field(default_factory=list)
    total_duration_ms: int = 0
