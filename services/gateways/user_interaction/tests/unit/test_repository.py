"""Unit tests for user interaction persistence helpers."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.chat_agent.db.repository import (
    MAX_CONVERSATION_BYTES,
    ConversationRepository,
    DailyProgressRepository,
)
from shared.observability.privacy import hash_identifier


@pytest.mark.asyncio
async def test_daily_progress_create_batch_uses_domain_aggregate() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    repo = DailyProgressRepository(session)

    records = await repo.create_batch(
        [
            {
                "user_id": "ou_user_1",
                "user_name": "Alice",
                "date": date(2026, 5, 23),
                "task_record_id": "rec_task_1",
                "task_title": "Ship DDD refactor",
                "status": "blocked",
                "raw_reply": "blocked by API",
                "note": "waiting",
            }
        ]
    )

    assert len(records) == 1
    assert records[0].status == "blocked"
    assert records[0].raw_reply == "blocked by API"
    assert records[0].note == "waiting"
    session.add.assert_called_once_with(records[0])
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_progress_create_batch_rejects_missing_user_id() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    repo = DailyProgressRepository(session)

    with pytest.raises(ValueError, match="requires user_id"):
        await repo.create_batch(
            [
                {
                    "user_id": "",
                    "user_name": "Alice",
                    "date": date(2026, 5, 23),
                    "task_record_id": "rec_task_1",
                    "task_title": "Ship DDD refactor",
                    "status": "pending",
                }
            ]
        )

    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_conversation_trim_log_uses_user_hash() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    repo = ConversationRepository(session)
    messages = [
        {"role": "user", "content": "x" * (MAX_CONVERSATION_BYTES + 1)},
        {"role": "assistant", "content": "ok"},
    ]

    with patch("agents.chat_agent.db.repository.logger") as logger:
        await repo.save("ou_raw_user", messages)

    warning = logger.warning.call_args
    assert warning.args == ("conversation_trimmed",)
    assert warning.kwargs["user_hash"] == hash_identifier("ou_raw_user")
    assert "user_id" not in warning.kwargs


@pytest.mark.asyncio
async def test_daily_progress_status_change_drains_domain_event() -> None:
    session = MagicMock()
    progress = SimpleNamespace(
        id=7,
        user_id="ou_raw_user",
        task_record_id="rec_task_1",
        task_title="Ship DDD refactor",
        status="pending",
        raw_reply="",
        note="",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = progress
    session.execute = AsyncMock(return_value=result)
    session.flush = AsyncMock()
    repo = DailyProgressRepository(session)

    with patch("agents.chat_agent.db.repository.logger") as logger:
        updated = await repo.update_progress(
            progress_id=7,
            status="completed",
            raw_reply="done",
            note="merged",
        )

    assert updated is progress
    assert progress.status == "completed"
    assert progress.raw_reply == "done"
    assert progress.note == "merged"
    info = logger.info.call_args
    assert info.args == ("daily_progress_status_changed",)
    assert info.kwargs["user_hash"] == hash_identifier("ou_raw_user")
    assert info.kwargs["task_record_hash"] == hash_identifier("rec_task_1")
    assert info.kwargs["from_status"] == "pending"
    assert info.kwargs["to_status"] == "completed"
    assert "user_id" not in info.kwargs
    assert "task_record_id" not in info.kwargs
