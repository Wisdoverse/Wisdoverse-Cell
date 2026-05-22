"""Tests for the Evolution UoW in-memory adapter (DDD-010 impl step)."""

from __future__ import annotations

from typing import Any

import pytest

from shared.capabilities.evolution.core.unit_of_work_ports import (
    EvolutionUnitOfWork,
)
from shared.capabilities.evolution.db.in_memory_unit_of_work import (
    InMemoryEvolutionUnitOfWork,
    in_memory_evolution_uow,
)


class _StubSeedStore:
    async def list_seeds(self, *args, **kwargs):
        return []

    async def upsert(self, *args, **kwargs):
        return None


class _StubOutbox:
    async def enqueue(self, *args, **kwargs):
        return None

    async def list_pending(self, limit: int = 100):
        return []


def test_in_memory_uow_has_protocol_surface() -> None:
    uow = InMemoryEvolutionUnitOfWork(
        seed_store=_StubSeedStore(),
        outbox=_StubOutbox(),
    )
    assert hasattr(uow, "seed_store")
    assert hasattr(uow, "outbox")
    assert hasattr(uow, "completed")
    assert callable(uow.commit)
    assert callable(uow.rollback)
    assert EvolutionUnitOfWork in InMemoryEvolutionUnitOfWork.__mro__


@pytest.mark.asyncio
async def test_commit_marks_completed() -> None:
    uow = InMemoryEvolutionUnitOfWork(
        seed_store=_StubSeedStore(),
        outbox=_StubOutbox(),
    )
    await uow.commit()
    assert uow.completed


@pytest.mark.asyncio
async def test_rollback_unmarks_completed() -> None:
    uow = InMemoryEvolutionUnitOfWork(
        seed_store=_StubSeedStore(),
        outbox=_StubOutbox(),
    )
    await uow.commit()
    await uow.rollback()
    assert not uow.completed


@pytest.mark.asyncio
async def test_commit_after_rollback_raises() -> None:
    uow = InMemoryEvolutionUnitOfWork(
        seed_store=_StubSeedStore(),
        outbox=_StubOutbox(),
    )
    await uow.rollback()
    with pytest.raises(RuntimeError, match="cannot commit a rolled-back"):
        await uow.commit()


@pytest.mark.asyncio
async def test_context_manager_commits_on_clean_exit() -> None:
    async with in_memory_evolution_uow(
        seed_store=_StubSeedStore(),
        outbox=_StubOutbox(),
    ) as uow:
        pass
    assert uow.completed


@pytest.mark.asyncio
async def test_context_manager_rolls_back_on_exception() -> None:
    captured: Any = None
    try:
        async with in_memory_evolution_uow(
            seed_store=_StubSeedStore(),
            outbox=_StubOutbox(),
        ) as uow:
            captured = uow
            raise ValueError("simulated failure")
    except ValueError:
        pass
    assert captured is not None
    assert not captured.completed
