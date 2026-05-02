from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class ConversationHistory(Base):
    """聊天历史"""
    __tablename__ = "chat_agent_conversation_histories"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, unique=True, index=True)
    messages = Column(Text)  # JSON serialized
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
