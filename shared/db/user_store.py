"""SQLAlchemy adapter for inbound user identity persistence."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identity_ports import UserIdentityStore
from shared.models.platform import Platform
from shared.models.user import User

from .repository import UserRepository


class SqlAlchemyUserIdentityStore(UserIdentityStore):
    """Session-scoped SQLAlchemy-backed user identity store."""

    def __init__(self, session: AsyncSession):
        self._users = UserRepository(session)

    async def create(self, user: User) -> User:
        return await self._users.create(user)

    async def get_by_id(self, user_id: str) -> User | None:
        return await self._users.get_by_id(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._users.get_by_email(email)

    async def get_by_platform_id(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> User | None:
        return await self._users.get_by_platform_id(platform, platform_user_id)

    async def update(self, user: User) -> User:
        return await self._users.update(user)
