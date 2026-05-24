"""Explicit unit-of-work boundary for Control Plane command paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .store_factory import ControlPlaneStores

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ControlPlaneUnitOfWork:
    """Session-scoped transaction boundary for Control Plane commands.

    Command handlers use this object to access aggregate stores and must call
    ``commit()`` after the application use case succeeds. Dependency cleanup
    rolls back any uncommitted unit of work.
    """

    __slots__ = ("_completed", "_session", "_stores")

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session
        self._stores = ControlPlaneStores(session)
        self._completed = False

    @property
    def stores(self) -> ControlPlaneStores:
        return self._stores

    @property
    def completed(self) -> bool:
        return self._completed

    async def commit(self) -> None:
        await self._session.commit()
        self._completed = True

    def begin_next_transaction(self) -> None:
        """Mark the unit of work active for a follow-up local transaction."""
        self._completed = False

    async def rollback(self) -> None:
        await self._session.rollback()
        self._completed = True


__all__ = ["ControlPlaneUnitOfWork"]
