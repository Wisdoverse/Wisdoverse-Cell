"""Ports for shared identity/user boundaries."""
from __future__ import annotations

from typing import Protocol

from shared.models.platform import Platform
from shared.models.user import User


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
