"""
Chat message persistence model.
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import IDPrefix, generate_id

from .base import Base


class ChatMessage(Base):
    """
    Group chat message table.

    Stores messages collected from Feishu group chats for context enrichment,
    continuous extraction, and conversation history.
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.MESSAGE)
    )

    # Chat and message identifiers
    chat_id: Mapped[str] = mapped_column(String(64))  # Group chat ID
    message_id: Mapped[str] = mapped_column(String(64), unique=True)  # Original Feishu message ID

    # Sender metadata
    sender_id: Mapped[str] = mapped_column(String(64))  # Sender open_id
    sender_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Sender name

    # Message content
    message_type: Mapped[str] = mapped_column(String(16))  # text/image/file/post
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Text content

    # Session and requirement associations
    session_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # Session ID
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)  # Related requirement ID list

    # Processing state
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)  # Whether requirements have been extracted

    # Timestamps
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Message sent time
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )  # Persistence time

    __table_args__ = (
        Index('ix_chat_messages_chat_session', 'chat_id', 'session_id'),
        Index('ix_chat_messages_sent_at', 'sent_at'),
        Index('ix_chat_messages_extracted', 'extracted'),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} chat_id={self.chat_id} message_type={self.message_type}>"
