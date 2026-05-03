from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class AlertLog(Base):
    """Alert log."""

    __tablename__ = "pjm_agent_alert_logs"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('deadline', 'overload', 'progress', 'blocked')", name="ck_alert_type"
        ),
        CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_alert_severity"),
    )

    id = Column(Integer, primary_key=True)
    alert_type = Column(String(50), nullable=False)  # deadline, overload, progress, blocked
    target = Column(String(200))
    message = Column(Text)
    severity = Column(String(20), nullable=False)  # critical, warning, info
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PMConfigCache(Base):
    """PJM configuration cache."""

    __tablename__ = "pjm_agent_config_cache"
    __table_args__ = (
        CheckConstraint(
            "config_type IN ('members', 'projects', 'rules', 'workload')", name="ck_config_type"
        ),
    )

    id = Column(Integer, primary_key=True)
    config_type = Column(
        String(50), nullable=False, unique=True
    )  # members, projects, rules, workload
    config_data = Column(Text)  # JSON
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DecompositionRecord(Base):
    """Task decomposition record."""

    __tablename__ = "pjm_agent_decomposition_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'failed')",
            name="ck_decompose_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    wp_id = Column(Integer, nullable=False, unique=True)
    project_id = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    assignee_id = Column(Integer)  # OP user ID, nullable
    decompose_result = Column(JSONB)
    approved_by = Column(String(100))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
