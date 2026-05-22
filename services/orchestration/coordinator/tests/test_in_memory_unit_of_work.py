"""Tests for the CoordinatorUnitOfWork in-memory adapter (DDD-010 impl step)."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest

from services.orchestration.coordinator.core.unit_of_work_ports import (
    CoordinatorUnitOfWork,
)
from services.orchestration.coordinator.db.in_memory_unit_of_work import (
    InMemoryCoordinatorUnitOfWork,
    in_memory_coordinator_uow,
)


class _StubStateStore:
    async def update_agent_state(self, agent_id, **_kwargs):
        return None

    async def get_agent_states(self):
        return {}

    async def get_pending_decisions(self):
        return []

    async def persist(self, decisions):
        return None


class _StubOutbox:
    async def enqueue(self, *args, **kwargs):
        return None

    async def list_pending(self, limit: int = 100):
        return []


def test_in_memory_uow_has_protocol_surface() -> None:
    """Verify the adapter exposes the CoordinatorUnitOfWork Protocol shape.

    The CoordinatorUnitOfWork Protocol is not ``@runtime_checkable``
    (it has class attributes not methods), so structural-conformance
    is checked by method presence here rather than isinstance().
    """
    uow = InMemoryCoordinatorUnitOfWork(
        state_store=_StubStateStore(),
        outbox=_StubOutbox(),
    )
    assert hasattr(uow, "state_store")
    assert hasattr(uow, "outbox")
    assert hasattr(uow, "completed")
    assert callable(uow.commit)
    assert callable(uow.rollback)
    # And the class explicitly extends the Protocol.
    assert CoordinatorUnitOfWork in InMemoryCoordinatorUnitOfWork.__mro__


@pytest.mark.asyncio
async def test_commit_marks_completed() -> None:
    uow = InMemoryCoordinatorUnitOfWork(
        state_store=_StubStateStore(),
        outbox=_StubOutbox(),
    )
    await uow.commit()
    assert uow.completed


@pytest.mark.asyncio
async def test_rollback_unmarks_completed() -> None:
    uow = InMemoryCoordinatorUnitOfWork(
        state_store=_StubStateStore(),
        outbox=_StubOutbox(),
    )
    await uow.commit()
    await uow.rollback()
    assert not uow.completed


@pytest.mark.asyncio
async def test_commit_after_rollback_raises() -> None:
    uow = InMemoryCoordinatorUnitOfWork(
        state_store=_StubStateStore(),
        outbox=_StubOutbox(),
    )
    await uow.rollback()
    with pytest.raises(RuntimeError, match="cannot commit a rolled-back"):
        await uow.commit()


@pytest.mark.asyncio
async def test_context_manager_commits_on_clean_exit() -> None:
    async with in_memory_coordinator_uow(
        state_store=_StubStateStore(),
        outbox=_StubOutbox(),
    ) as uow:
        # caller did not explicitly commit; manager auto-commits.
        pass
    assert uow.completed


@pytest.mark.asyncio
async def test_context_manager_rolls_back_on_exception() -> None:
    captured: Any = None
    try:
        async with in_memory_coordinator_uow(
            state_store=_StubStateStore(),
            outbox=_StubOutbox(),
        ) as uow:
            captured = uow
            raise ValueError("simulated failure")
    except ValueError:
        pass
    assert captured is not None
    assert not captured.completed
