from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.requirement_context_queries import (
    RequirementContextQueryService,
)


def _requirement_row(context_message_ids: list[str] | None = None):
    return SimpleNamespace(
        id="req_test",
        title="Test requirement",
        description="Test description",
        status="pending",
        priority="high",
        category="Feature",
        source_quote="source",
        confirmed_by=None,
        confirmed_at=None,
        created_at=datetime.now(UTC),
        context_message_ids=context_message_ids or [],
    )


def _message_row(message_id: str, session_id: str = "ses_test"):
    timestamp = datetime.now(UTC)
    return SimpleNamespace(
        id=message_id,
        sender_name="Test User",
        content="Test content",
        message_type="text",
        sent_at=timestamp,
        session_id=session_id,
    )


@pytest.mark.asyncio
async def test_get_context_returns_requirement_messages_and_session_metadata():
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(
        return_value=_requirement_row(["msg_1", "msg_2"]),
    )

    now = datetime.now(UTC)
    message_repo = AsyncMock()
    context_messages = [
        _message_row("msg_1"),
        _message_row("msg_2"),
    ]
    session_messages = [
        SimpleNamespace(sent_at=now),
        SimpleNamespace(sent_at=now + timedelta(minutes=5)),
    ]
    message_repo.get_by_id = AsyncMock(side_effect=context_messages)
    message_repo.get_by_session = AsyncMock(return_value=session_messages)

    result = await RequirementContextQueryService(
        requirement_repository=requirement_repo,
        message_repository=message_repo,
    ).get_context("req_test")

    assert result is not None
    assert result.requirement.id == "req_test"
    assert [message.id for message in result.context_messages] == ["msg_1", "msg_2"]
    assert result.session is not None
    assert result.session.session_id == "ses_test"
    assert result.session.total_messages == 2
    assert result.session.started_at == now
    assert result.session.ended_at == now + timedelta(minutes=5)
    requirement_repo.get_by_id.assert_awaited_once_with("req_test")
    message_repo.get_by_session.assert_awaited_once_with("ses_test")


@pytest.mark.asyncio
async def test_get_context_ignores_missing_context_messages():
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(
        return_value=_requirement_row(["msg_1", "msg_missing"]),
    )

    message_repo = AsyncMock()
    message_repo.get_by_id = AsyncMock(side_effect=[_message_row("msg_1"), None])
    message_repo.get_by_session = AsyncMock(return_value=[])

    result = await RequirementContextQueryService(
        requirement_repository=requirement_repo,
        message_repository=message_repo,
    ).get_context("req_test")

    assert result is not None
    assert [message.id for message in result.context_messages] == ["msg_1"]
    assert result.session is not None
    assert result.session.total_messages == 0


@pytest.mark.asyncio
async def test_get_context_returns_none_for_missing_requirement():
    requirement_repo = AsyncMock()
    requirement_repo.get_by_id = AsyncMock(return_value=None)
    message_repo = AsyncMock()

    result = await RequirementContextQueryService(
        requirement_repository=requirement_repo,
        message_repository=message_repo,
    ).get_context("req_missing")

    assert result is None
    message_repo.get_by_id.assert_not_called()
