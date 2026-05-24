"""
User Model - unified user table.

Maps identities across Feishu, WeCom, Web, and other platform accounts.
"""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.identifiers import UserId
from shared.core.identity_domain import (
    IdentityDomainEvent,
    IdentityState,
    InvalidIdentityTransitionError,
    PlatformLinked,
    PlatformUserRef,
    UserActivated,
    UserCreated,
    identity_state_for,
    normalize_email,
    normalize_phone,
)
from shared.core.ids import IDPrefix, generate_id
from shared.db.base import Base
from shared.models.platform import Platform


class User(Base):
    """Unified user table with cross-platform identity mappings."""
    __tablename__ = "users"
    __allow_unmapped__ = True

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

    @classmethod
    def create_identity(
        cls,
        *,
        user_id: UserId,
        name: str,
        platform_ref: PlatformUserRef,
        email: str | None = None,
        phone: str | None = None,
        occurred_at: datetime | None = None,
    ) -> "User":
        """Create a user aggregate through the Identity boundary."""
        timestamp = occurred_at or datetime.now(UTC)
        user = cls(
            id=str(user_id),
            email=normalize_email(email),
            phone=normalize_phone(phone),
            name=name.strip() or "Unknown",
            created_at=timestamp,
            last_active_at=timestamp,
        )
        user._append_domain_event(
            UserCreated(
                user_id=UserId(user.id),
                name=user.name,
                email=user.email,
                phone=user.phone,
                occurred_at=timestamp,
            )
        )
        user.link_platform_account(platform_ref, occurred_at=timestamp)
        return user

    @property
    def identity_state(self) -> IdentityState:
        """Return the derived identity lifecycle state."""
        return identity_state_for(
            has_platform_link=any(
                (
                    self.feishu_open_id,
                    self.wecom_user_id,
                    self.web_user_id,
                )
            ),
            last_active_platform=self.last_active_platform,
        )

    def link_platform_account(
        self,
        platform_ref: PlatformUserRef,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        """Link a platform account while enforcing aggregate invariants."""
        if platform_ref.platform == Platform.OPENCLAW:
            self._append_domain_event(
                PlatformLinked(
                    user_id=UserId(self.id),
                    platform=platform_ref.platform,
                    platform_user_id=platform_ref.platform_user_id,
                    occurred_at=occurred_at or datetime.now(UTC),
                )
            )
            return

        current_value = self._get_platform_identity(platform_ref.platform)
        if current_value and current_value != platform_ref.platform_user_id:
            raise InvalidIdentityTransitionError(
                f"user {self.id} is already linked to another {platform_ref.platform.value} id"
            )
        if current_value == platform_ref.platform_user_id:
            return

        self._set_platform_identity(platform_ref.platform, platform_ref.platform_user_id)
        self._append_domain_event(
            PlatformLinked(
                user_id=UserId(self.id),
                platform=platform_ref.platform,
                platform_user_id=platform_ref.platform_user_id,
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )

    def record_activity(
        self,
        platform: Platform,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        """Record a valid platform activity transition for this user."""
        if platform != Platform.OPENCLAW and self._get_platform_identity(platform) is None:
            raise InvalidIdentityTransitionError(
                f"user {self.id} must link {platform.value} before activity is recorded"
            )

        timestamp = occurred_at or datetime.now(UTC)
        self.last_active_at = timestamp
        self.last_active_platform = platform.value
        self._append_domain_event(
            UserActivated(
                user_id=UserId(self.id),
                platform=platform,
                occurred_at=timestamp,
            )
        )

    def pull_domain_events(self) -> list[IdentityDomainEvent]:
        """Drain in-memory domain events raised by aggregate methods."""
        events = list(self.__dict__.get("_domain_events", []))
        self.__dict__["_domain_events"] = []
        return events

    def _append_domain_event(self, event: IdentityDomainEvent) -> None:
        events = self.__dict__.setdefault("_domain_events", [])
        events.append(event)

    def _get_platform_identity(self, platform: Platform) -> str | None:
        if platform == Platform.FEISHU:
            return self.feishu_open_id
        if platform == Platform.WECOM:
            return self.wecom_user_id
        if platform == Platform.WEB:
            return self.web_user_id
        raise InvalidIdentityTransitionError(
            f"platform {platform.value!r} is not an identity platform"
        )

    def _set_platform_identity(self, platform: Platform, platform_user_id: str) -> None:
        if platform == Platform.FEISHU:
            self.feishu_open_id = platform_user_id
            return
        if platform == Platform.WECOM:
            self.wecom_user_id = platform_user_id
            return
        if platform == Platform.WEB:
            self.web_user_id = platform_user_id
            return
        raise InvalidIdentityTransitionError(
            f"platform {platform.value!r} is not an identity platform"
        )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} name={self.name}>"
