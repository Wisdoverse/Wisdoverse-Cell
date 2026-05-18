"""
SyncModule DB Models

PostgreSQL models migrated from the historical feishu-to-openproject flow.
"""
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class SyncMapping(Base):
    """OpenProject work package ID to Feishu record ID mapping."""
    __tablename__ = "sync_agent_mappings"

    id = Column(Integer, primary_key=True)
    op_work_package_id = Column(Integer, nullable=False, unique=True, index=True)
    feishu_record_id = Column(String(64), index=True)
    op_project_id = Column(Integer)
    title = Column(String(500))
    last_op_update = Column(DateTime(timezone=True))
    last_feishu_update = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class SubtaskMapping(Base):
    """Feishu record mapping for subtasks."""
    __tablename__ = "sync_agent_subtask_mappings"

    id = Column(Integer, primary_key=True)
    parent_op_id = Column(Integer, nullable=False, index=True)
    feishu_record_id = Column(String(64), nullable=False, unique=True, index=True)
    subtask_name = Column(String(500))
    subtask_status = Column(String(50))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class SyncLog(Base):
    """Sync operation log."""
    __tablename__ = "sync_agent_logs"
    __table_args__ = (
        CheckConstraint("sync_type IN ('op_to_feishu', 'feishu_to_op', 'full')", name="ck_sync_type"),
        CheckConstraint("status IN ('started', 'completed', 'failed')", name="ck_sync_status"),
    )

    id = Column(Integer, primary_key=True)
    sync_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True))


class SyncLock(Base):
    """Distributed lock."""
    __tablename__ = "sync_agent_locks"

    id = Column(Integer, primary_key=True)
    lock_name = Column(String(100), nullable=False, unique=True, index=True)
    locked_by = Column(String(100))
    locked_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_locked = Column(Boolean, default=False)


class SyncEventOutbox(Base):
    """Durable outbox for Sync integration events."""

    __tablename__ = "sync_agent_event_outbox"

    event_id = Column(String(32), primary_key=True)
    event_type = Column(String(100), nullable=False, index=True)
    source_agent = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    schema_version = Column(String(16), nullable=False, default="1.0")
    trace_id = Column(String(64), nullable=True)
    correlation_id = Column(String(64), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    published_at = Column(DateTime(timezone=True), nullable=True)
