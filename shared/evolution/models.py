"""
Evolution Data Models — foundation for self-evolution system.

Models:
- LLMCallRecord: tracks a single LLM API call with cost computation
- SkillConfig: versioned skill configuration
- ExecutionTrace: complete trace of one handle_event execution
- Reflection: output of self-reflector analysis
"""

from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from shared.core.ids import generate_id

# ── Cost table (USD per token) ──────────────────────────────────────────────

_COST_PER_TOKEN: dict[str, tuple[float, float]] = {
    # model_id: (input_cost_per_token, output_cost_per_token)
    "claude-opus-4-6": (15.0 / 1_000_000, 75.0 / 1_000_000),
    "claude-sonnet-4-20250514": (3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-haiku-4-5-20251001": (0.80 / 1_000_000, 4.0 / 1_000_000),
}


# ── Enums ───────────────────────────────────────────────────────────────────


class SkillStatus(StrEnum):
    """Lifecycle status of a skill configuration."""

    ACTIVE = "active"
    CANDIDATE = "candidate"
    RETIRED = "retired"


# ── LLMCallRecord ──────────────────────────────────────────────────────────


class LLMCallRecord(BaseModel):
    """Tracks a single LLM API call."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    call_id: str = Field(default_factory=lambda: generate_id("llm"))
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    success: bool
    error: Optional[str] = None
    called_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_usd(self) -> float:
        """Compute cost in USD based on model pricing."""
        rates = _COST_PER_TOKEN.get(self.model_id)
        if rates is None:
            return 0.0
        input_rate, output_rate = rates
        return (self.prompt_tokens * input_rate) + (
            self.completion_tokens * output_rate
        )


# ── SkillConfig ─────────────────────────────────────────────────────────────


class SkillConfig(BaseModel):
    """Versioned skill configuration for an agent capability."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    skill_id: str
    version: int
    status: SkillStatus = SkillStatus.ACTIVE
    system_prompt: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    few_shot_examples: list[dict[str, Any]] = Field(default_factory=list)
    output_format: Optional[str] = None
    target_model: Optional[str] = None
    total_executions: int = 0
    success_rate: float = 0.0
    avg_human_rating: float = 0.0
    promoted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── ExecutionTrace ──────────────────────────────────────────────────────────


class ExecutionTrace(BaseModel):
    """Complete trace of one handle_event execution."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    trace_id: str
    agent_id: str
    event_type: str
    input_event: Optional[dict[str, Any]] = None
    output_events: list[dict[str, Any]] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    skill_used: Optional[str] = None
    skill_version: Optional[int] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None
    human_rating: Optional[int] = None
    human_correction: Optional[str] = None
    auto_score: Optional[float] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> Optional[float]:
        """Compute execution duration in milliseconds."""
        if self.completed_at is None:
            return None
        delta = self.completed_at - self.started_at
        return delta.total_seconds() * 1000.0


# ── Reflection ──────────────────────────────────────────────────────────────


class Reflection(BaseModel):
    """Output of self-reflector analysis."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    reflection_id: str = Field(default_factory=lambda: generate_id("ref"))
    agent_id: str
    skill_id: str
    success_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    optimization_suggestions: list[str] = Field(default_factory=list)
    human_corrections_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Experiment ─────────────────────────────────────────────────────────────


class ExperimentStatus(str, Enum):
    """Lifecycle status of an A/B experiment."""

    RUNNING = "running"
    PROMOTED = "promoted"
    CONCLUDED = "concluded"
    ROLLED_BACK = "rolled_back"


class Experiment(BaseModel):
    """Tracks an A/B experiment between two skill versions."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    experiment_id: str = Field(default_factory=lambda: generate_id("exp"))
    agent_id: str
    skill_id: str
    control_version: int
    candidate_version: int
    traffic_pct: int = Field(default=10, le=30)
    min_samples: int = 50
    max_duration_hours: int = 72
    success_metric: str = "success_rate"
    min_improvement: float = 0.05
    status: ExperimentStatus = ExperimentStatus.RUNNING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    concluded_at: datetime | None = None

    @field_validator("traffic_pct")
    @classmethod
    def cap_traffic_pct(cls, v: int) -> int:
        """Cap traffic percentage at 30%."""
        if v > 30:
            raise ValueError("traffic_pct must not exceed 30")
        return v


# ── MemoryEntry ────────────────────────────────────────────────────────────


class MemoryType(str, Enum):
    """Type of agent memory entry."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryEntry(BaseModel):
    """A key-value memory entry for an agent."""

    agent_id: str
    memory_type: MemoryType
    key: str
    value: dict[str, Any]
    ttl_seconds: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
