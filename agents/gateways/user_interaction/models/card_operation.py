from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base


class CardOperation(Base):
    __tablename__ = "chat_agent_card_operations"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_name = Column(String(100), nullable=False, default="")
    action = Column(String(50), nullable=False, index=True)
    table_id = Column(String(100), nullable=False, default="")
    record_id = Column(String(100), nullable=False, default="")
    assignee_name = Column(String(100), nullable=False, default="")
    fields_snapshot = Column(Text, default="{}")
    result = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
