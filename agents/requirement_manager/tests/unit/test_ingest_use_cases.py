from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.ingest_use_cases import IngestUseCase


def _agent_result():
    return SimpleNamespace(
        meeting_id="mtg_test",
        requirements_extracted=2,
        questions_generated=1,
    )


@pytest.mark.asyncio
async def test_upload_content_parses_date_and_delegates_to_agent():
    repository = AsyncMock()
    agent = AsyncMock()
    agent.ingest_meeting = AsyncMock(return_value=_agent_result())
    session = MagicMock()

    result = await IngestUseCase(
        meeting_repository=repository,
        agent=agent,
        session=session,
    ).upload_content(
        content="Meeting content",
        source="upload",
        title="Planning",
        meeting_date="2026-05-17T10:00:00Z",
        participants=["Alice"],
        context="Sprint planning",
    )

    assert result.meeting_id == "mtg_test"
    agent.ingest_meeting.assert_awaited_once()
    call_kwargs = agent.ingest_meeting.call_args.kwargs
    assert call_kwargs["session"] is session
    assert call_kwargs["meeting_date"] == datetime.fromisoformat(
        "2026-05-17T10:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_feishu_ingest_returns_existing_meeting_without_agent_call():
    repository = AsyncMock()
    repository.get_by_source_id = AsyncMock(return_value=SimpleNamespace(id="mtg_old"))
    agent = AsyncMock()

    result = await IngestUseCase(
        meeting_repository=repository,
        agent=agent,
        session=MagicMock(),
    ).ingest_feishu(
        summary="Meeting summary",
        meeting_id="feishu_1",
    )

    assert result.meeting_id == "mtg_old"
    assert result.requirements_extracted == 0
    assert result.questions_generated == 0
    assert result.deduplicated is True
    agent.ingest_meeting.assert_not_called()


@pytest.mark.asyncio
async def test_feishu_ingest_delegates_new_meeting_to_agent():
    repository = AsyncMock()
    repository.get_by_source_id = AsyncMock(return_value=None)
    agent = AsyncMock()
    agent.ingest_meeting = AsyncMock(return_value=_agent_result())
    session = MagicMock()

    result = await IngestUseCase(
        meeting_repository=repository,
        agent=agent,
        session=session,
    ).ingest_feishu(
        summary="Meeting summary",
        meeting_id="feishu_1",
        topic="Planning",
        participants=["Alice"],
        meeting_time="invalid-date",
    )

    assert result.meeting_id == "mtg_test"
    agent.ingest_meeting.assert_awaited_once_with(
        content="Meeting summary",
        source="feishu",
        session=session,
        title="Planning",
        meeting_date=None,
        participants=["Alice"],
        source_id="feishu_1",
    )
