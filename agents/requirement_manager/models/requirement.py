"""
Requirement Model - 需求数据模型
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.ids import IDPrefix, generate_id

from .base import Base


class RequirementStatus(str, Enum):
    """需求状态"""
    PENDING = "pending"         # 待确认
    CONFIRMED = "confirmed"     # 已确认
    CHANGED = "changed"         # 已变更
    REJECTED = "rejected"       # 已拒绝


class RequirementPriority(str, Enum):
    """需求优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementCategory(str, Enum):
    """需求分类"""
    FEATURE = "功能"
    PERFORMANCE = "性能"
    HARDWARE = "硬件"
    INTEGRATION = "集成"
    UI = "UI"
    SECURITY = "安全"
    OTHER = "其他"


class Requirement(Base):
    """
    需求表

    存储从会议记录中提取的结构化需求。
    """
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.REQUIREMENT)
    )

    # 核心信息
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    source_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 原文引用

    # 分类
    status: Mapped[str] = mapped_column(String(32), default=RequirementStatus.PENDING.value)
    priority: Mapped[str] = mapped_column(String(32), default=RequirementPriority.MEDIUM.value)
    category: Mapped[str] = mapped_column(String(32), default=RequirementCategory.FEATURE.value)

    # 来源关联
    source_meeting_ids: Mapped[list] = mapped_column(JSON, default=list)  # 关联的会议ID列表
    context_message_ids: Mapped[list] = mapped_column(JSON, default=list)  # 关联的聊天消息ID列表

    # 确认信息
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 变更历史
    history: Mapped[list] = mapped_column(JSON, default=list)  # 变更记录列表

    # 时间戳（使用 timezone-aware datetime）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # 关联的问题
    open_questions: Mapped[list["OpenQuestion"]] = relationship(
        "OpenQuestion",
        back_populates="requirement",
        cascade="all, delete-orphan"
    )

    def add_history(self, action: str, detail: str, by: str):
        """添加变更历史"""
        entry = {
            "action": action,
            "detail": detail,
            "by": by,
            "at": datetime.now(UTC).isoformat()
        }
        self.history = self.history + [entry]

    def __repr__(self) -> str:
        return f"<Requirement id={self.id} title={self.title} status={self.status}>"


class OpenQuestion(Base):
    """
    待确认问题表

    存储从需求中自动生成的待确认问题。
    """
    __tablename__ = "open_questions"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.QUESTION)
    )

    # 关联需求
    requirement_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    requirement: Mapped["Requirement"] = relationship(
        "Requirement",
        back_populates="open_questions"
    )

    # 问题内容
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 为什么要问

    # 回答
    status: Mapped[str] = mapped_column(String(32), default="open")  # open / answered
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 时间戳（使用 timezone-aware datetime）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<OpenQuestion id={self.id} status={self.status}>"
