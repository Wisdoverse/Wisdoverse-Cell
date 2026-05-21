from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.ingest_use_cases import IngestUseCase


def _agent_result():
    return SimpleNamespace(
        meeting_id="mtg_test",
        requirements_extracted=2,
        questions_generated=1,
    )


class FakeUnitOfWork:
    def __init__(self):
        self.completed = False
        self.committed = False
        self.rolled_back = False
        self.meetings = AsyncMock()

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


@pytest.mark.asyncio
async def test_upload_content_parses_date_and_delegates_to_agent():
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(return_value=_agent_result())
    agent.publish_ingest_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await IngestUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).upload_content(
        content="Meeting content",
        source="upload",
        title="Planning",
        meeting_date="2026-05-17T10:00:00Z",
        participants=["Alice"],
        context="Sprint planning",
    )

    assert result.meeting_id == "mtg_test"
    assert uow.committed is True
    agent.ingest_meeting_with_uow.assert_awaited_once()
    agent.publish_ingest_side_effects.assert_awaited_once()
    call_kwargs = agent.ingest_meeting_with_uow.call_args.kwargs
    assert call_kwargs["uow"] is uow
    assert call_kwargs["meeting_date"] == datetime.fromisoformat(
        "2026-05-17T10:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_feishu_ingest_returns_existing_meeting_without_agent_call():
    uow = FakeUnitOfWork()
    uow.meetings.get_by_source_id = AsyncMock(return_value=SimpleNamespace(id="mtg_old"))
    agent = AsyncMock()
    agent.publish_ingest_side_effects = AsyncMock()

    result = await IngestUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).ingest_feishu(
        summary="Meeting summary",
        meeting_id="feishu_1",
    )

    assert result.meeting_id == "mtg_old"
    assert result.requirements_extracted == 0
    assert result.questions_generated == 0
    assert result.deduplicated is True
    assert uow.rolled_back is True
    agent.ingest_meeting_with_uow.assert_not_called()
    agent.publish_ingest_side_effects.assert_not_called()


@pytest.mark.asyncio
async def test_feishu_ingest_delegates_new_meeting_to_agent():
    uow = FakeUnitOfWork()
    uow.meetings.get_by_source_id = AsyncMock(return_value=None)
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(return_value=_agent_result())
    agent.publish_ingest_side_effects = AsyncMock()

    result = await IngestUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).ingest_feishu(
        summary="Meeting summary",
        meeting_id="feishu_1",
        topic="Planning",
        participants=["Alice"],
        meeting_time="invalid-date",
    )

    assert result.meeting_id == "mtg_test"
    assert uow.committed is True
    agent.ingest_meeting_with_uow.assert_awaited_once_with(
        content="Meeting summary",
        source="feishu",
        uow=uow,
        title="Planning",
        meeting_date=None,
        participants=["Alice"],
        source_id="feishu_1",
    )
    agent.publish_ingest_side_effects.assert_awaited_once()
