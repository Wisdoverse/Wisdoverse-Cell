from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def _session_factory(session):
    @asynccontextmanager
    async def session_context():
        yield session

    return session_context


def _use_case(
    *,
    agent: AsyncMock | None = None,
    session: object | None = None,
) -> RequirementManagerRequestUseCase:
    if agent is None:
        agent = AsyncMock()
        agent.ingest_meeting = AsyncMock(return_value=_agent_result())
    if session is None:
        session = MagicMock()

    return RequirementManagerRequestUseCase(
        agent=agent,
        session_factory=_session_factory(session),
    )


@pytest.mark.asyncio
async def test_ingest_request_validates_and_delegates_to_agent() -> None:
    agent = AsyncMock()
    agent.ingest_meeting = AsyncMock(return_value=_agent_result())
    session = MagicMock()

    result = await _use_case(agent=agent, session=session).handle(
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
    agent.ingest_meeting.assert_awaited_once()
    kwargs = agent.ingest_meeting.await_args.kwargs
    assert kwargs["content"] == "We need a login flow."
    assert kwargs["source"] == "control_plane"
    assert kwargs["session"] is session
    assert kwargs["title"] == "Planning"
    assert kwargs["meeting_date"].isoformat() == "2026-05-03T10:30:00+00:00"
    assert kwargs["participants"] == ["Alice", "Bob"]
    assert kwargs["context"] == "Sprint planning"
    assert kwargs["source_id"] == "meeting_123"


@pytest.mark.asyncio
async def test_ingest_request_rejects_missing_content_without_opening_session() -> None:
    opened = False

    @asynccontextmanager
    async def session_context():
        nonlocal opened
        opened = True
        yield MagicMock()

    agent = AsyncMock()
    use_case = RequirementManagerRequestUseCase(
        agent=agent,
        session_factory=session_context,
    )

    result = await use_case.handle({"action": "ingest"})

    assert result == {"status": "error", "error": "content_required"}
    assert opened is False
    agent.ingest_meeting.assert_not_called()


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
    agent.ingest_meeting = AsyncMock(return_value=_agent_result())

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

    kwargs = agent.ingest_meeting.await_args.kwargs
    assert kwargs["source"] == "agent_request"
    assert kwargs["participants"] == ["Alice"]
    assert kwargs["title"] == "123"
    assert kwargs["context"] == "456"
    assert kwargs["source_id"] == "789"


@pytest.mark.asyncio
async def test_unknown_request_returns_existing_ok_contract() -> None:
    result = await _use_case().handle({"action": "unknown"})

    assert result == {"status": "ok"}
