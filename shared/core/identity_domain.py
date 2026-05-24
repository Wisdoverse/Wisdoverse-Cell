"""Domain value objects and events for the Identity / User boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from shared.core.identifiers import UserId

if TYPE_CHECKING:
    from shared.models.platform import Platform


class InvalidIdentityValueError(ValueError):
    """Raised when an identity value object is invalid."""


class InvalidIdentityTransitionError(ValueError):
    """Raised when a user aggregate transition violates identity invariants."""


class IdentityState(StrEnum):
    """Derived lifecycle state for a unified user identity."""

    UNLINKED = "unlinked"
    LINKED = "linked"
    ACTIVE = "active"


SUPPORTED_IDENTITY_PLATFORMS = frozenset({"feishu", "wecom", "web", "openclaw"})


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """Normalized email address value object."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized:
            raise InvalidIdentityValueError("email address must not be empty")
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise InvalidIdentityValueError("email address must contain a local and domain part")
        if len(normalized) > 128:
            raise InvalidIdentityValueError("email address must be at most 128 characters")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """Normalized phone number value object."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().replace(" ", "").replace("-", "")
        if not normalized:
            raise InvalidIdentityValueError("phone number must not be empty")
        body = normalized[1:] if normalized.startswith("+") else normalized
        if not body.isdigit():
            raise InvalidIdentityValueError("phone number must contain digits only")
        if len(normalized) > 32:
            raise InvalidIdentityValueError("phone number must be at most 32 characters")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PlatformUserRef:
    """Platform-specific identity reference after adapter translation."""

    platform: Platform
    platform_user_id: str

    def __post_init__(self) -> None:
        platform_value = _platform_value(self.platform)
        if platform_value not in SUPPORTED_IDENTITY_PLATFORMS:
            raise InvalidIdentityValueError(
                f"platform {platform_value!r} is not an identity platform"
            )
        normalized_id = self.platform_user_id.strip()
        if not normalized_id:
            raise InvalidIdentityValueError("platform user id must not be empty")
        if len(normalized_id) > 128:
            raise InvalidIdentityValueError("platform user id must be at most 128 characters")
        object.__setattr__(self, "platform_user_id", normalized_id)


@dataclass(frozen=True, slots=True)
class IdentityDomainEvent:
    """Base immutable in-memory domain event for identity aggregates."""

    user_id: UserId
    occurred_at: datetime

    @property
    def event_name(self) -> str:
        """Return the stable class-name event identifier."""
        return type(self).__name__

    def to_payload(self) -> dict[str, Any]:
        """Return a primitive payload for future outbox adapters."""
        payload = asdict(self)
        payload["user_id"] = str(self.user_id)
        if "platform" in payload:
            payload["platform"] = _platform_value(payload["platform"])
        return payload


@dataclass(frozen=True, slots=True)
class UserCreated(IdentityDomainEvent):
    """Raised when a unified user identity is created."""

    name: str
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class PlatformLinked(IdentityDomainEvent):
    """Raised when a platform account is linked to a unified user."""

    platform: Platform
    platform_user_id: str


@dataclass(frozen=True, slots=True)
class UserActivated(IdentityDomainEvent):
    """Raised when a user resolves through a platform and becomes active."""

    platform: Platform


def normalize_email(value: str | None) -> str | None:
    """Normalize an optional email address for persistence and lookup."""
    if value is None:
        return None
    return str(EmailAddress(value))


def normalize_phone(value: str | None) -> str | None:
    """Normalize an optional phone number for persistence and lookup."""
    if value is None:
        return None
    return str(PhoneNumber(value))


def identity_state_for(
    *,
    has_platform_link: bool,
    last_active_platform: str | None,
) -> IdentityState:
    """Derive the identity lifecycle state from persisted user fields."""
    if last_active_platform:
        return IdentityState.ACTIVE
    if has_platform_link:
        return IdentityState.LINKED
    return IdentityState.UNLINKED


def _platform_value(platform: Platform) -> str:
    value = getattr(platform, "value", platform)
    return str(value)


__all__ = [
    "EmailAddress",
    "IdentityDomainEvent",
    "IdentityState",
    "InvalidIdentityTransitionError",
    "InvalidIdentityValueError",
    "PhoneNumber",
    "PlatformLinked",
    "PlatformUserRef",
    "SUPPORTED_IDENTITY_PLATFORMS",
    "UserActivated",
    "UserCreated",
    "identity_state_for",
    "normalize_email",
    "normalize_phone",
]
