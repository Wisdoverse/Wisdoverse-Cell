"""
Feedback Model - Records user corrections for learning.

Stores examples of user corrections to extracted requirements,
enabling continuous improvement of extraction accuracy.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FeedbackRecord(Base):
    """
    User feedback/correction record for learning.

    Captures when users modify extracted requirements, providing
    training examples to improve future extraction.
    """

    __tablename__ = "feedback_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # fb_ + ULID

    # Reference
    requirement_id: Mapped[str] = mapped_column(String(36), index=True)  # req_ + ULID
    meeting_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # mtg_ + ULID

    # Original extraction
    original_title: Mapped[str] = mapped_column(Text)
    original_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    original_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # User correction
    corrected_title: Mapped[str] = mapped_column(Text)
    corrected_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    corrected_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Context
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_type: Mapped[str] = mapped_column(
        String(20), default="correction"
    )  # correction, rejection, merge

    # Metadata
    corrected_by: Mapped[str] = mapped_column(String(100))
    correction_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Usage tracking
    used_in_prompt: Mapped[bool] = mapped_column(default=False)
    effectiveness_score: Mapped[Optional[float]] = mapped_column(nullable=True)

    def to_example(self) -> dict:
        """Convert to a prompt example format."""
        return {
            "source_text": self.source_text or "",
            "original": {
                "title": self.original_title,
                "description": self.original_description,
                "priority": self.original_priority,
                "category": self.original_category,
            },
            "corrected": {
                "title": self.corrected_title,
                "description": self.corrected_description,
                "priority": self.corrected_priority,
                "category": self.corrected_category,
            },
            "feedback_type": self.feedback_type,
        }

    def __repr__(self) -> str:
        return f"<FeedbackRecord {self.id} req={self.requirement_id}>"
