"""Tests for the Control Plane unit-of-work boundary."""

from __future__ import annotations

from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.unit_of_work import ControlPlaneUnitOfWork


class _SessionStub:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


async def test_control_plane_unit_of_work_exposes_stores_and_commits() -> None:
    session = _SessionStub()
    uow = ControlPlaneUnitOfWork(session)  # type: ignore[arg-type]

    assert isinstance(uow.stores, ControlPlaneStores)
    assert uow.completed is False

    await uow.commit()

    assert session.commits == 1
    assert session.rollbacks == 0
    assert uow.completed is True


async def test_control_plane_unit_of_work_rolls_back() -> None:
    session = _SessionStub()
    uow = ControlPlaneUnitOfWork(session)  # type: ignore[arg-type]

    await uow.rollback()

    assert session.commits == 0
    assert session.rollbacks == 1
    assert uow.completed is True


async def test_control_plane_unit_of_work_supports_sequential_local_transactions() -> None:
    session = _SessionStub()
    uow = ControlPlaneUnitOfWork(session)  # type: ignore[arg-type]

    await uow.commit()
    uow.begin_next_transaction()

    assert uow.completed is False

    await uow.commit()

    assert session.commits == 2
    assert uow.completed is True
