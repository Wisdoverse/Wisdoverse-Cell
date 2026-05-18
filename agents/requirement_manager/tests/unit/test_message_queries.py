from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.message_queries import MessageQueryService


def _message_row(
    *,
    session_id: str = "ses_test",
    extracted: bool = False,
    requirement_ids: list[str] | None = None,
    sent_at: datetime | None = None,
):
    timestamp = sent_at or datetime.now(UTC)
    return SimpleNamespace(
        id="msg_test",
        chat_id="oc_test",
        message_id="om_test",
        sender_id="ou_test",
        sender_name="Test User",
        message_type="text",
        content="Test content",
        session_id=session_id,
        extracted=extracted,
        requirement_ids=requirement_ids,
        sent_at=timestamp,
        created_at=timestamp,
    )


@pytest.mark.asyncio
async def test_search_messages_returns_paginated_read_model():
    row = _message_row()
    repository = AsyncMock()
    repository.search = AsyncMock(return_value=([row], 5))

    result = await MessageQueryService(repository).search_messages(
        chat_id="oc_test",
        keyword="OAuth",
        sender_id="ou_test",
        page=2,
        page_size=2,
    )

    assert result.total == 5
    assert result.page == 2
    assert result.page_size == 2
    assert result.total_pages == 3
    assert result.messages[0].message_id == "om_test"
    repository.search.assert_awaited_once_with(
        keyword="OAuth",
        chat_id="oc_test",
        sender_id="ou_test",
        start_time=None,
        end_time=None,
        page=2,
        page_size=2,
    )


@pytest.mark.asyncio
async def test_get_session_messages_returns_metadata():
    now = datetime.now(UTC)
    repository = AsyncMock()
    repository.get_by_session = AsyncMock(
        return_value=[
            _message_row(
                session_id="ses_test",
                extracted=False,
                requirement_ids=["req_001"],
                sent_at=now,
            ),
            _message_row(
                session_id="ses_test",
                extracted=True,
                requirement_ids=["req_002"],
                sent_at=now + timedelta(minutes=5),
            ),
        ],
    )

    result = await MessageQueryService(repository).get_session_messages("ses_test")

    assert result is not None
    assert result.session_id == "ses_test"
    assert result.chat_id == "oc_test"
    assert result.message_count == 2
    assert result.started_at == now
    assert result.ended_at == now + timedelta(minutes=5)
    assert result.extracted is True
    assert set(result.requirement_ids) == {"req_001", "req_002"}
    repository.get_by_session.assert_awaited_once_with("ses_test")


@pytest.mark.asyncio
async def test_get_session_messages_returns_none_for_missing_session():
    repository = AsyncMock()
    repository.get_by_session = AsyncMock(return_value=[])

    result = await MessageQueryService(repository).get_session_messages("ses_missing")

    assert result is None
