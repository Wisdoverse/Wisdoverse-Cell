from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.daily_progress_queries import (
    DailyProgressQueryService,
)


@pytest.mark.asyncio
async def test_list_progress_returns_read_models_and_calculates_range():
    repository = AsyncMock()
    repository.get_by_date_range = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                user_id="u_1",
                user_name="Alice",
                date=date(2026, 5, 17),
                task_record_id="rec_1",
                task_title="Ship backend boundary",
                status="done",
                note=None,
                raw_reply=None,
            )
        ]
    )

    result = await DailyProgressQueryService(repository).list_progress(
        target_date=date(2026, 5, 17),
        user_id="u_1",
        days=3,
    )

    repository.get_by_date_range.assert_awaited_once_with(
        date(2026, 5, 15),
        date(2026, 5, 17),
        user_id="u_1",
    )
    assert result[0].id == 1
    assert result[0].task_title == "Ship backend boundary"
    assert result[0].note == ""
    assert result[0].raw_reply == ""


@pytest.mark.asyncio
async def test_list_progress_response_serializes_read_models():
    repository = AsyncMock()
    repository.get_by_date_range = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                user_id="u_1",
                user_name="Alice",
                date=date(2026, 5, 17),
                task_record_id="rec_1",
                task_title="Ship backend boundary",
                status="done",
                note=None,
                raw_reply=None,
            )
        ]
    )

    result = await DailyProgressQueryService(repository).list_progress_response(
        target_date=date(2026, 5, 17),
        user_id="u_1",
        days=1,
    )

    assert result == {
        "entries": [
            {
                "id": 1,
                "user_id": "u_1",
                "user_name": "Alice",
                "date": "2026-05-17",
                "task_record_id": "rec_1",
                "task_title": "Ship backend boundary",
                "status": "done",
                "note": "",
                "raw_reply": "",
            }
        ],
        "total": 1,
    }
