from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class UserInteractionEventOutbox(Base):
    """Durable outbox for user-interaction gateway integration events."""

    __tablename__ = "chat_agent_event_outbox"

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
