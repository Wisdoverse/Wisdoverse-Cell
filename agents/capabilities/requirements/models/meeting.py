"""
Meeting Model - 会议记录数据模型
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.utils.id_generator import IDPrefix, generate_id

from .base import Base


class Meeting(Base):
    """
    会议记录表

    存储从飞书会议、微信等渠道获取的会议纪要/聊天记录。
    """
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.MEETING)
    )

    # 来源信息
    source: Mapped[str] = mapped_column(String(32))  # "feishu" / "upload" / "wechat"
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 原始系统的ID

    # 内容
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # 会议主题
    raw_content: Mapped[str] = mapped_column(Text)  # 原始内容

    # 元数据
    meeting_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # 参与者列表
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 上下文说明

    # 处理状态
    processed: Mapped[bool] = mapped_column(default=False)  # 是否已提取需求
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} source={self.source} title={self.title}>"
