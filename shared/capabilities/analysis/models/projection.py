"""SQLAlchemy tables for the Analysis projection (DDD-004 follow-up).

Production-grade persistence for the projection seeded in
``shared/capabilities/analysis/core/domain/projection.py``. Mirrors
the value-object shape one-to-one so the SQLAlchemy adapter can
round-trip rows without lossy mapping.

Per ``data-ownership.md`` §1.8, these tables are append/replace
projections, never sources of truth. The Analysis capability owns
both the tables and the consumer that refreshes them from upstream
domain events.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class AnalysisWorkPackageProjection(Base):
    """Projected snapshot of one OpenProject work package."""

    __tablename__ = "analysis_work_package_projection"

    wp_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=True, index=True)
    subject = Column(String(512), nullable=False)
    type_name = Column(String(64), nullable=True)
    status_name = Column(String(64), nullable=False)
    percentage_done = Column(Integer, nullable=False, default=0)
    assigned_to = Column(String(128), nullable=True)
    parent_id = Column(Integer, nullable=True, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    extra = Column(JSONB, nullable=False, default=dict)


class AnalysisSubtaskProgressProjection(Base):
    """Projected snapshot of one Feishu Bitable subtask record."""

    __tablename__ = "analysis_subtask_progress_projection"

    subtask_record_id = Column(String(64), primary_key=True)
    parent_wp_id = Column(Integer, nullable=False, index=True)
    subtask_status = Column(String(64), nullable=False)
    completed = Column(Boolean, nullable=False, default=False)
    title = Column(String(512), nullable=False, default="")
    blocked_reason = Column(String(512), nullable=False, default="")
    feature_id = Column(String(64), nullable=True, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
