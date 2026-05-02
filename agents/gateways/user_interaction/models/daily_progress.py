from datetime import UTC, datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from .base import Base


class DailyProgress(Base):
    __tablename__ = "chat_agent_daily_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_name = Column(String(100), nullable=False, default="")
    date = Column(Date, nullable=False, index=True)
    task_record_id = Column(String(100), nullable=False, default="")
    task_title = Column(String(500), nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending")
    raw_reply = Column(Text, default="")
    note = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
