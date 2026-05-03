"""
User Model - unified user table.

Maps identities across Feishu, WeCom, Web, and other platform accounts.
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import IDPrefix, generate_id
from shared.db.base import Base


class User(Base):
    """Unified user table with cross-platform identity mappings."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=lambda: generate_id(IDPrefix.USER)
    )

    # Identity fields
    email: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(32), unique=True, nullable=True, index=True
    )

    # Basic profile
    name: Mapped[str] = mapped_column(String(64))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Platform account mappings
    feishu_open_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    feishu_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wecom_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    web_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    # Activity metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )
    last_active_platform: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} name={self.name}>"
