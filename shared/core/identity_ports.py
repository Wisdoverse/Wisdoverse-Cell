"""Ports for shared identity/user boundaries."""
from __future__ import annotations

from typing import Protocol

from shared.models.platform import Platform
from shared.models.user import User
from shared.schemas.event import Event


class UserIdentityStore(Protocol):
    """Persistence operations required by identity resolution use cases."""

    async def create(self, user: User) -> User:
        """Persist a new user."""

    async def get_by_id(self, user_id: str) -> User | None:
        """Return a user by unified user id."""

    async def get_by_email(self, email: str) -> User | None:
        """Return a user by email address."""

    async def get_by_platform_id(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> User | None:
        """Return a user by platform-specific id."""

    async def update(self, user: User) -> User:
        """Persist changes to a user."""


class IdentityEventOutboxStore(Protocol):
    """Persistence operations for identity integration-event staging."""

    async def add(self, event: Event) -> None:
        """Store an integration event in the local transaction outbox."""

    async def list_pending(self, limit: int = 100) -> list[object]:
        """Return pending identity event outbox rows."""

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure while leaving the row retryable."""
