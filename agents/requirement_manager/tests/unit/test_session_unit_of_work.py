"""Requirement legacy session unit-of-work adapter tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.db.unit_of_work import (
    SqlAlchemyRequirementSessionUnitOfWork,
)
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_session_unit_of_work_uses_injected_stores_and_commits_session():
    session = MagicMock()
    session.commit = AsyncMock()
    outbox_store = MagicMock()
    requirements = MagicMock()
    questions = MagicMock()

    uow = SqlAlchemyRequirementSessionUnitOfWork(
        session,
        outbox_store=outbox_store,
        requirements=requirements,
        questions=questions,
    )

    await uow.commit()

    assert uow.requirements is requirements
    assert uow.questions is questions
    session.commit.assert_awaited_once()
    assert uow.completed is True


@pytest.mark.asyncio
async def test_session_unit_of_work_rolls_back_session():
    session = MagicMock()
    session.rollback = AsyncMock()
    outbox_store = MagicMock()

    uow = SqlAlchemyRequirementSessionUnitOfWork(
        session,
        outbox_store=outbox_store,
    )

    await uow.rollback()

    session.rollback.assert_awaited_once()
    assert uow.completed is True


@pytest.mark.asyncio
async def test_session_unit_of_work_stages_outbox_in_caller_session():
    session = MagicMock()
    outbox_store = MagicMock()
    outbox_store.stage = AsyncMock()
    event = Event.create(
        event_type=EventTypes.REQUIREMENT_CONFIRMED,
        source_agent="requirement-manager",
        payload={"requirement_id": "req_1"},
    )
    uow = SqlAlchemyRequirementSessionUnitOfWork(
        session,
        outbox_store=outbox_store,
    )

    await uow.outbox.stage(event)

    outbox_store.stage.assert_awaited_once_with(session, event)
