from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.request_use_cases import (
    RequirementManagerRequestUseCase,
)


def _agent_result():
    return SimpleNamespace(
        meeting_id="mtg_123",
        requirements_extracted=2,
        questions_generated=1,
        requirement_ids=["req_1", "req_2"],
    )


class FakeUnitOfWork:
    def __init__(self):
        self.completed = False
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.completed = True
        self.committed = True

    async def rollback(self):
        self.completed = True
        self.rolled_back = True


def _uow_factory(uow):
    @asynccontextmanager
    async def uow_context():
        try:
            yield uow
        finally:
            if not uow.completed:
                await uow.rollback()

    return uow_context


def _use_case(
    *,
    agent: AsyncMock | None = None,
    uow: FakeUnitOfWork | None = None,
) -> RequirementManagerRequestUseCase:
    if agent is None:
        agent = AsyncMock()
        agent.ingest_meeting_with_uow = AsyncMock(return_value=_agent_result())
        agent.publish_ingest_side_effects = AsyncMock()
    if uow is None:
        uow = FakeUnitOfWork()

    return RequirementManagerRequestUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    )


@pytest.mark.asyncio
async def test_ingest_request_validates_and_delegates_to_agent() -> None:
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(return_value=_agent_result())
    agent.publish_ingest_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await _use_case(agent=agent, uow=uow).handle(
        {
            "action": "ingest",
            "content": "We need a login flow.",
            "source": "control_plane",
            "title": "Planning",
            "meeting_date": "2026-05-03T10:30:00Z",
            "participants": ["Alice", "Bob"],
            "context": "Sprint planning",
            "source_id": "meeting_123",
        }
    )

    assert result == {
        "status": "ok",
        "meeting_id": "mtg_123",
        "requirements_extracted": 2,
        "questions_generated": 1,
        "requirement_ids": ["req_1", "req_2"],
    }
    assert uow.committed is True
    agent.ingest_meeting_with_uow.assert_awaited_once()
    agent.publish_ingest_side_effects.assert_awaited_once()
    kwargs = agent.ingest_meeting_with_uow.await_args.kwargs
    assert kwargs["content"] == "We need a login flow."
    assert kwargs["source"] == "control_plane"
    assert kwargs["uow"] is uow
    assert kwargs["title"] == "Planning"
    assert kwargs["meeting_date"].isoformat() == "2026-05-03T10:30:00+00:00"
    assert kwargs["participants"] == ["Alice", "Bob"]
    assert kwargs["context"] == "Sprint planning"
    assert kwargs["source_id"] == "meeting_123"


@pytest.mark.asyncio
async def test_ingest_request_rejects_missing_content_without_opening_session() -> None:
    opened = False

    @asynccontextmanager
    async def uow_context():
        nonlocal opened
        opened = True
        yield FakeUnitOfWork()

    agent = AsyncMock()
    use_case = RequirementManagerRequestUseCase(
        agent=agent,
        uow_factory=uow_context,
    )

    result = await use_case.handle({"action": "ingest"})

    assert result == {"status": "error", "error": "content_required"}
    assert opened is False
    agent.ingest_meeting_with_uow.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_request_rejects_invalid_meeting_date() -> None:
    result = await _use_case().handle(
        {
            "action": "ingest",
            "content": "A real note",
            "meeting_date": "not-a-date",
        }
    )

    assert result == {
        "status": "error",
        "error": "meeting_date_must_be_iso_datetime",
    }


@pytest.mark.asyncio
async def test_ingest_request_normalizes_scalar_optional_fields() -> None:
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(return_value=_agent_result())
    agent.publish_ingest_side_effects = AsyncMock()

    await _use_case(agent=agent).handle(
        {
            "action": "ingest",
            "content": "A real note",
            "source": "",
            "participants": "Alice",
            "title": 123,
            "context": 456,
            "source_id": 789,
        }
    )

    kwargs = agent.ingest_meeting_with_uow.await_args.kwargs
    assert kwargs["source"] == "agent_request"
    assert kwargs["participants"] == ["Alice"]
    assert kwargs["title"] == "123"
    assert kwargs["context"] == "456"
    assert kwargs["source_id"] == "789"


@pytest.mark.asyncio
async def test_unknown_request_returns_existing_ok_contract() -> None:
    result = await _use_case().handle({"action": "unknown"})

    assert result == {"status": "ok"}
