"""Identity event outbox persistence model."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from shared.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityEventOutbox(Base):
    """Durable outbox for identity integration events."""

    __tablename__ = "identity_event_outbox"

    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_agent: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_identity_event_outbox_status_created", "status", "created_at"),
    )
