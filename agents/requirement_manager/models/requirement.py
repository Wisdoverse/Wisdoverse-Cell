"""
Requirement persistence model.
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.ids import IDPrefix, generate_id

from .base import Base


class RequirementStatus(str, Enum):
    """Requirement status."""
    PENDING = "pending"         # Waiting for confirmation
    CONFIRMED = "confirmed"     # Confirmed
    CHANGED = "changed"         # Changed
    REJECTED = "rejected"       # Rejected


class RequirementPriority(str, Enum):
    """Requirement priority."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementCategory(str, Enum):
    """Requirement category."""
    FEATURE = "功能"
    PERFORMANCE = "性能"
    HARDWARE = "硬件"
    INTEGRATION = "集成"
    UI = "UI"
    SECURITY = "安全"
    OTHER = "其他"


class Requirement(Base):
    """
    Requirement table.

    Stores structured requirements extracted from meeting records.
    """
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.REQUIREMENT)
    )

    # Core information
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    source_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Source quote

    # Classification
    status: Mapped[str] = mapped_column(String(32), default=RequirementStatus.PENDING.value)
    priority: Mapped[str] = mapped_column(String(32), default=RequirementPriority.MEDIUM.value)
    category: Mapped[str] = mapped_column(String(32), default=RequirementCategory.FEATURE.value)

    # Source associations
    source_meeting_ids: Mapped[list] = mapped_column(JSON, default=list)  # Related meeting ID list
    context_message_ids: Mapped[list] = mapped_column(JSON, default=list)  # Related chat message ID list

    # Confirmation metadata
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Change history
    history: Mapped[list] = mapped_column(JSON, default=list)  # Change entry list

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

    # Related questions
    open_questions: Mapped[list["OpenQuestion"]] = relationship(
        "OpenQuestion",
        back_populates="requirement",
        cascade="all, delete-orphan"
    )

    def add_history(self, action: str, detail: str, by: str):
        """Append a change-history entry."""
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
    Open question table.

    Stores open questions generated from requirements.
    """
    __tablename__ = "open_questions"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.QUESTION)
    )

    # Related requirement
    requirement_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    requirement: Mapped["Requirement"] = relationship(
        "Requirement",
        back_populates="open_questions"
    )

    # Question content
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Why this question is needed

    # Answer
    status: Mapped[str] = mapped_column(String(32), default="open")  # open / answered
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps use timezone-aware datetime values.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<OpenQuestion id={self.id} status={self.status}>"
