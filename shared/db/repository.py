"""
User Repository - user data access layer.

Provides user CRUD operations and cross-platform lookup helpers.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.platform import Platform
from shared.models.user import User


class UserRepository:
    """User data repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:
        """Create a user."""
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        """Get a user by phone."""
        result = await self.session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_by_platform_id(
        self, platform: Platform, platform_user_id: str
    ) -> Optional[User]:
        """Get a user by platform-specific ID."""
        column_map = {
            Platform.FEISHU: User.feishu_open_id,
            Platform.WECOM: User.wecom_user_id,
            Platform.WEB: User.web_user_id,
        }
        column = column_map.get(platform)
        if not column:
            return None

        result = await self.session.execute(
            select(User).where(column == platform_user_id)
        )
        return result.scalar_one_or_none()

    async def update(self, user: User) -> User:
        """Update a user."""
        await self.session.flush()
        await self.session.refresh(user)
        return user
