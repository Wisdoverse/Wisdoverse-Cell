"""Requirement session extraction use case tests."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.meeting_ingest_workflow import IngestResult
from agents.requirement_manager.core.session_extraction_use_cases import (
    RequirementSessionExtractionUseCase,
    format_messages_for_extraction,
)


class FakeMessages:
    def __init__(self, messages):
        self._messages = messages
        self.marked: list[tuple[str, list[str]]] = []

    async def get_by_session(self, session_id: str):
        return self._messages

    async def mark_extracted(self, session_id: str, requirement_ids: list[str]):
        self.marked.append((session_id, requirement_ids))


class FakeRequirements:
    def __init__(self, requirement):
        self._requirement = requirement
        self.requested_ids: list[str] = []

    async def get_by_id(self, requirement_id: str):
        self.requested_ids.append(requirement_id)
        return self._requirement


class FakeUnitOfWork:
    def __init__(self, messages, requirement=None):
        self.messages = FakeMessages(messages)
        self.requirements = FakeRequirements(requirement)
        self.committed = False

    async def commit(self):
        self.committed = True


def _uow_factory(uow):
    @asynccontextmanager
    async def context():
        yield uow

    return context


def _message(**overrides):
    values = {
        "id": "msg_1",
        "chat_id": "chat_1",
        "sender_name": "Alice",
        "sent_at": datetime(2026, 5, 22, 10, 30, tzinfo=UTC),
        "content": "We need offline capture",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_extract_from_session_ingests_marks_links_and_sends_card():
    requirement = SimpleNamespace(context_message_ids=[])
    uow = FakeUnitOfWork([_message()], requirement=requirement)
    agent = AsyncMock()
    ingest_result = IngestResult(
        meeting_id="mtg_1",
        requirements_extracted=1,
        questions_generated=0,
        requirement_ids=["req_1"],
    )
    agent.ingest_meeting_with_uow = AsyncMock(return_value=ingest_result)
    agent.publish_ingest_side_effects = AsyncMock()
    agent.send_session_extraction_card = AsyncMock()

    result = await RequirementSessionExtractionUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).extract_from_session("ses_1")

    assert result is ingest_result
    agent.ingest_meeting_with_uow.assert_awaited_once()
    ingest_kwargs = agent.ingest_meeting_with_uow.await_args.kwargs
    assert ingest_kwargs["source"] == "feishu_session"
    assert ingest_kwargs["uow"] is uow
    assert "Session ses_1 from chat chat_1" in ingest_kwargs["context"]
    assert uow.messages.marked == [("ses_1", ["req_1"])]
    assert requirement.context_message_ids == ["msg_1"]
    assert uow.committed is True
    agent.publish_ingest_side_effects.assert_awaited_once_with(ingest_result)
    agent.send_session_extraction_card.assert_awaited_once_with(
        "chat_1",
        ingest_result,
        "ses_1",
    )


@pytest.mark.asyncio
async def test_extract_from_session_without_messages_returns_none():
    uow = FakeUnitOfWork([])
    agent = AsyncMock()

    result = await RequirementSessionExtractionUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).extract_from_session("ses_empty")

    assert result is None
    assert uow.committed is False
    agent.ingest_meeting_with_uow.assert_not_called()


@pytest.mark.asyncio
async def test_extract_from_session_without_requirements_skips_card_and_linking():
    uow = FakeUnitOfWork([_message()])
    agent = AsyncMock()
    ingest_result = IngestResult(
        meeting_id="mtg_1",
        requirements_extracted=0,
        questions_generated=0,
        requirement_ids=[],
    )
    agent.ingest_meeting_with_uow = AsyncMock(return_value=ingest_result)
    agent.publish_ingest_side_effects = AsyncMock()
    agent.send_session_extraction_card = AsyncMock()

    result = await RequirementSessionExtractionUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).extract_from_session("ses_1")

    assert result is ingest_result
    assert uow.messages.marked == []
    assert uow.requirements.requested_ids == []
    assert uow.committed is True
    agent.publish_ingest_side_effects.assert_awaited_once_with(ingest_result)
    agent.send_session_extraction_card.assert_not_awaited()


def test_format_messages_for_extraction_skips_empty_content_and_fills_defaults():
    result = format_messages_for_extraction(
        [
            _message(sender_name=None),
            _message(content="  "),
            _message(sent_at=None, sender_name="Bob", content="Second item"),
        ],
    )

    assert result == "[10:30] Unknown: We need offline capture\n[??:??] Bob: Second item"
