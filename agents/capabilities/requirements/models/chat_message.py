"""
ChatMessage Model - 群聊消息数据模型
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.utils.id_generator import IDPrefix, generate_id

from .base import Base


class ChatMessage(Base):
    """
    群聊消息表

    存储从飞书群聊获取的消息，用于上下文丰富、持续抽取和会话历史。
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.MESSAGE)
    )

    # 群聊和消息标识
    chat_id: Mapped[str] = mapped_column(String(64))  # 群聊 ID
    message_id: Mapped[str] = mapped_column(String(64), unique=True)  # 飞书原始消息 ID

    # 发送者信息
    sender_id: Mapped[str] = mapped_column(String(64))  # 发送者 open_id
    sender_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # 发送者姓名

    # 消息内容
    message_type: Mapped[str] = mapped_column(String(16))  # text/image/file/post
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 文本内容

    # 会话和需求关联
    session_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 会话 ID
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)  # 关联的需求 ID 列表

    # 处理状态
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否已提取需求

    # 时间戳
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 消息发送时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )  # 入库时间

    __table_args__ = (
        Index('ix_chat_messages_chat_session', 'chat_id', 'session_id'),
        Index('ix_chat_messages_sent_at', 'sent_at'),
        Index('ix_chat_messages_extracted', 'extracted'),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} chat_id={self.chat_id} message_type={self.message_type}>"
