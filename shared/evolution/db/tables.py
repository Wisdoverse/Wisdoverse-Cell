"""
Evolution SQLAlchemy table definitions.

All tables prefixed with ``evolution_`` to avoid collisions.
Uses ``JSON`` type (not ``JSONB``) for SQLite compatibility in tests;
PostgreSQL will store these as ``json`` which is sufficient.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

evolution_metadata = MetaData()


class EvolutionBase(DeclarativeBase):
    metadata = evolution_metadata


# ── evolution_event_outbox ───────────────────────────────────────────────────


class EvolutionEventOutbox(EvolutionBase):
    __tablename__ = "evolution_event_outbox"

    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_agent: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="1.0",
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_evolution_event_outbox_event_type", "event_type"),
        Index("ix_evolution_event_outbox_status", "status"),
    )


# ── evolution_traces ───────────────────────────────────────────────────────


class EvolutionTrace(EvolutionBase):
    __tablename__ = "evolution_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    input_event: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    llm_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    skill_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    skill_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    human_correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_evolution_traces_agent_skill", "agent_id", "skill_used"),
    )


# ── evolution_skill_configs ────────────────────────────────────────────────


class EvolutionSkillConfig(EvolutionBase):
    __tablename__ = "evolution_skill_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    few_shot_examples: Mapped[list | None] = mapped_column(JSON, nullable=True)
    output_format: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    total_executions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_human_rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_id_version"),
    )


# ── evolution_reflections ──────────────────────────────────────────────────


class EvolutionReflection(EvolutionBase):
    __tablename__ = "evolution_reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    success_patterns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    failure_patterns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    optimization_suggestions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    human_corrections_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


# ── evolution_experiments ─────────────────────────────────────────────────


class EvolutionExperiment(EvolutionBase):
    __tablename__ = "evolution_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    traffic_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    min_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_duration_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=72
    )
    success_metric: Mapped[str] = mapped_column(
        String(64), nullable=False, default="success_rate"
    )
    min_improvement: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.05
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )
    control_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    candidate_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    concluded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ── evolution_memory ──────────────────────────────────────────────────────


class EvolutionMemory(EvolutionBase):
    __tablename__ = "evolution_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "key", name="uq_agent_id_key"),
    )


# ── evolution_collaboration_patterns ─────────────────────────────────────


class EvolutionCollaborationPatternTable(EvolutionBase):
    __tablename__ = "evolution_collaboration_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    trigger_event: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list | None] = mapped_column(JSON, default=list)
    shadow_results: Mapped[list | None] = mapped_column(JSON, default=list)
    production_results: Mapped[list | None] = mapped_column(JSON, default=list)
    human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
