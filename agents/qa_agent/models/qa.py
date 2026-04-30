from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from shared.utils.id_generator import generate_ulid

from .base import Base


class QAAcceptanceRun(Base):
    """QA 验收运行记录"""

    __tablename__ = "qa_acceptance_runs"

    id = Column(String(32), primary_key=True, default=generate_ulid)
    trace_id = Column(String(64), nullable=True)
    trigger_event_id = Column(String(64), nullable=True)
    agent_name = Column(String(100), nullable=False)
    target_path = Column(String(255), nullable=False)
    commit_sha = Column(String(40), nullable=True)
    branch = Column(String(255), nullable=True)
    mr_iid = Column(Integer, nullable=True)
    gitlab_project_id = Column(Integer, nullable=True)
    trigger = Column(String(20), nullable=False)  # event/api/manual/scheduled
    level = Column(String(10), nullable=False)  # l0/l1/l2/all
    l0_status = Column(String(10), nullable=False)  # PASS/FAIL
    l1_status = Column(String(10), nullable=False)  # PASS/WARN
    l2_status = Column(String(10), nullable=False)  # INFO
    total_checks = Column(Integer, nullable=False, default=0)
    l0_failure_count = Column(Integer, nullable=False, default=0)
    l1_warning_count = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    runner_exit_code = Column(Integer, nullable=False, default=0)
    files_changed = Column(JSONB, nullable=False, server_default="[]")
    raw_report = Column(JSONB, nullable=False)
    report_markdown = Column(Text, nullable=True)
    notification_summary = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    results = relationship("QAAcceptanceResult", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "trigger IN ('event', 'api', 'manual', 'scheduled')",
            name="ck_qa_run_trigger",
        ),
        CheckConstraint(
            "level IN ('l0', 'l1', 'l2', 'all')",
            name="ck_qa_run_level",
        ),
        CheckConstraint(
            "l0_status IN ('PASS', 'FAIL', 'ERROR')",
            name="ck_qa_run_l0_status",
        ),
        CheckConstraint(
            "l1_status IN ('PASS', 'WARN', 'ERROR')",
            name="ck_qa_run_l1_status",
        ),
        CheckConstraint("duration_seconds >= 0", name="ck_qa_run_duration"),
        Index("idx_qa_runs_agent_created_at", "agent_name", created_at.desc()),
        Index("idx_qa_runs_commit_sha", "commit_sha"),
        Index("idx_qa_runs_mr", "gitlab_project_id", "mr_iid"),
    )


class QAAcceptanceResult(Base):
    """QA 验收具体检查结果"""

    __tablename__ = "qa_acceptance_results"

    id = Column(String(32), primary_key=True, default=generate_ulid)
    run_id = Column(String(32), ForeignKey("qa_acceptance_runs.id"), nullable=False)
    level = Column(String(4), nullable=False)  # L0/L1/L2
    category = Column(String(64), nullable=False)
    check_name = Column(String(100), nullable=False)
    status = Column(String(10), nullable=False)  # PASS/FAIL/WARN/INFO/SKIP
    severity = Column(String(16), nullable=False)
    is_blocking = Column(Boolean, nullable=False, default=False)
    details = Column(Text, nullable=True)
    file_path = Column(String(255), nullable=True)
    line_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Relationships
    run = relationship("QAAcceptanceRun", back_populates="results")

    __table_args__ = (
        CheckConstraint("level IN ('L0', 'L1', 'L2')", name="ck_qa_result_level"),
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'WARN', 'INFO', 'SKIP')",
            name="ck_qa_result_status",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_qa_result_severity",
        ),
        Index("idx_qa_results_run_id", "run_id"),
        Index("idx_qa_results_level_status", "level", "status"),
        Index("idx_qa_results_check_name", "check_name"),
    )
