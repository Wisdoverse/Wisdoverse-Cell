"""
Meeting model for persisted meeting and channel records.
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import IDPrefix, generate_id

from .base import Base


class Meeting(Base):
    """
    Meeting records table.

    Stores meeting notes and chat records collected from Feishu meetings,
    WeCom, and other channels.
    """
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.MEETING)
    )

    # Source metadata
    source: Mapped[str] = mapped_column(String(32))  # "feishu" / "upload" / "wechat"
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Source-system ID

    # Content
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # Meeting subject
    raw_content: Mapped[str] = mapped_column(Text)  # Raw content

    # Metadata
    meeting_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list)  # Participant list
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Context notes

    # Processing state
    processed: Mapped[bool] = mapped_column(default=False)  # Whether requirements have been extracted
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps use timezone-aware datetime values.
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
