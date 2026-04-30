"""
SyncAgent DB Models

从 feishu-to-openproject 迁移，适配 PostgreSQL。
"""
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, Text

from .base import Base


class SyncMapping(Base):
    """OP work package ID ↔ 飞书 record ID 映射"""
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
    """子任务的飞书记录映射"""
    __tablename__ = "sync_agent_subtask_mappings"

    id = Column(Integer, primary_key=True)
    parent_op_id = Column(Integer, nullable=False, index=True)
    feishu_record_id = Column(String(64), nullable=False, unique=True, index=True)
    subtask_name = Column(String(500))
    subtask_status = Column(String(50))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class SyncLog(Base):
    """同步操作日志"""
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
    """分布式锁"""
    __tablename__ = "sync_agent_locks"

    id = Column(Integer, primary_key=True)
    lock_name = Column(String(100), nullable=False, unique=True, index=True)
    locked_by = Column(String(100))
    locked_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_locked = Column(Boolean, default=False)
