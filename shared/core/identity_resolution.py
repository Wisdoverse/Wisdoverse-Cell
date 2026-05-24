"""Application use cases for the Identity / User boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from shared.core.identifiers import UserId
from shared.core.identity_domain import (
    IdentityDomainEvent,
    InvalidIdentityValueError,
    PlatformUserRef,
    normalize_email,
)
from shared.core.identity_ports import UserIdentityStore
from shared.models.platform import Platform
from shared.models.user import User


class IdentityPlatformDirectoryPort(Protocol):
    """Platform user directory operations needed by identity resolution."""

    async def get_user_email(self, platform_user_id: str) -> str | None:
        """Return the user's platform email when available."""

    async def get_user_name(self, platform_user_id: str) -> str | None:
        """Return the user's platform display name when available."""


IdentityUserIdFactory = Callable[[], UserId]
InvalidIdentityValueHandler = Callable[[PlatformUserRef], None]


@dataclass(frozen=True, slots=True)
class IdentityResolutionResult:
    """Resolved user and aggregate events raised during the resolution."""

    user: User
    domain_events: tuple[IdentityDomainEvent | Any, ...]


class IdentityResolutionUseCase:
    """Resolve or create a unified user through identity ports."""

    def __init__(
        self,
        *,
        adapters: Mapping[Platform, IdentityPlatformDirectoryPort],
        user_id_factory: IdentityUserIdFactory,
        invalid_email_handler: InvalidIdentityValueHandler | None = None,
    ) -> None:
        self._adapters = adapters
        self._user_id_factory = user_id_factory
        self._invalid_email_handler = invalid_email_handler

    async def resolve(
        self,
        *,
        store: UserIdentityStore,
        platform_ref: PlatformUserRef,
    ) -> IdentityResolutionResult:
        """Resolve a platform identity, creating or linking a user if needed."""
        user = await store.get_by_platform_id(
            platform_ref.platform,
            platform_ref.platform_user_id,
        )

        if user is None:
            user = await self._create_or_link_user(store, platform_ref)

        user.record_activity(platform_ref.platform)
        await store.update(user)
        return IdentityResolutionResult(
            user=user,
            domain_events=tuple(user.pull_domain_events()),
        )

    async def _create_or_link_user(
        self,
        store: UserIdentityStore,
        platform_ref: PlatformUserRef,
    ) -> User:
        adapter = self._adapters.get(platform_ref.platform)
        if adapter is None:
            return await self._create_new_user(store, platform_ref, None, "Unknown")

        email = self._normalize_adapter_email(
            await adapter.get_user_email(platform_ref.platform_user_id),
            platform_ref,
        )
        name = await adapter.get_user_name(platform_ref.platform_user_id) or "Unknown"

        if email:
            existing_user = await store.get_by_email(email)
            if existing_user is not None:
                existing_user.link_platform_account(platform_ref)
                return existing_user

        return await self._create_new_user(store, platform_ref, email, name)

    async def _create_new_user(
        self,
        store: UserIdentityStore,
        platform_ref: PlatformUserRef,
        email: str | None,
        name: str,
    ) -> User:
        user = User.create_identity(
            user_id=self._user_id_factory(),
            email=email,
            name=name,
            platform_ref=platform_ref,
        )
        return await store.create(user)

    def _normalize_adapter_email(
        self,
        email: str | None,
        platform_ref: PlatformUserRef,
    ) -> str | None:
        try:
            return normalize_email(email)
        except InvalidIdentityValueError:
            if self._invalid_email_handler is not None:
                self._invalid_email_handler(platform_ref)
            return None


__all__ = [
    "IdentityPlatformDirectoryPort",
    "IdentityResolutionResult",
    "IdentityResolutionUseCase",
    "IdentityUserIdFactory",
    "InvalidIdentityValueHandler",
]
