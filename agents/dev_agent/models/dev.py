"""ORM models for dev_agent."""
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class DevAgentTask(Base):
    """Tracks each PJM task through the dev lifecycle."""

    __tablename__ = "dev_agent_tasks"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_dev_risk_level",
        ),
        CheckConstraint(
            "status IN ('pending','planning','awaiting_approval',"
            "'executing','security_scanning','mr_creating','mr_created',"
            "'qa_triggered','reviewing','completed','failed','expired')",
            name="ck_dev_status",
        ),
        Index("idx_dev_tasks_status", "status", "created_at"),
        Index("idx_dev_tasks_workflow_id", "workflow_id"),
        Index("idx_dev_tasks_mr_iid", "mr_iid"),
    )

    id = Column(String, primary_key=True)
    wp_id = Column(Integer, nullable=False, unique=True)
    task_title = Column(Text)
    risk_level = Column(String(10), default="MEDIUM")
    status = Column(String(30), default="pending")
    workflow_id = Column(String)
    mr_iid = Column(Integer)
    mr_url = Column(Text)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    failed_step = Column(String(50))
    workflow_started_at = Column(DateTime(timezone=True))
    last_polled_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True))


class DevAgentWorkflowLog(Base):
    """Workflow execution history + LLM audit log."""

    __tablename__ = "dev_agent_workflow_logs"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("dev_agent_tasks.id"))
    workflow_json = Column(JSONB)
    llm_request_prompt = Column(Text)
    llm_response_raw = Column(Text)
    tool_routing_json = Column(JSONB)
    node_results = Column(JSONB)
    total_duration_s = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
