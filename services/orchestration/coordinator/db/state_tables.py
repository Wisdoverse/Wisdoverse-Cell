"""SQLAlchemy table definitions for coordinator durable state (DDD-018).

Per ADR-0008 (`docs/adr/0008-coordinator-durable-state-store.md`), the
coordinator's per-agent state, workflow state, and pending-decision
queue persist to Postgres in the coordinator-owned schema, alongside
the existing `coordinator_event_outbox`.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CoordinatorAgentState(Base):
    """Per-agent runtime state as observed by the coordinator."""

    __tablename__ = "coordinator_agent_state"

    agent_id = Column(String(64), primary_key=True)
    status = Column(String(16), nullable=False, index=True)
    current_task = Column(String(64), nullable=True)
    last_output_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class CoordinatorWorkflowState(Base):
    """Active workflow state persisted by the coordinator."""

    __tablename__ = "coordinator_workflow_state"

    workflow_id = Column(String(64), primary_key=True)
    type = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, index=True)
    current_phase = Column(String(64), nullable=False)
    agents_involved = Column(JSONB, nullable=False)
    context = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class CoordinatorPendingDecision(Base):
    """Pending coordinator dispatch decision waiting for replay/resolution."""

    __tablename__ = "coordinator_pending_decision"

    decision_id = Column(String(32), primary_key=True)
    workflow_id = Column(String(64), nullable=True, index=True)
    reasoning = Column(Text, nullable=False)
    action = Column(String(64), nullable=False)
    target_agent = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=True)
    outcome = Column(String(32), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
        index=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
