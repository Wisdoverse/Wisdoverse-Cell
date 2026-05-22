"""Requirement read query orchestration tests."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.read_query_use_cases import (
    RequirementReadQueryUseCase,
)


class FakeUnitOfWork:
    def __init__(self):
        self.requirements = AsyncMock()
        self.meetings = AsyncMock()
        self.questions = AsyncMock()
        self.completed = False
        self.rolled_back = False

    async def rollback(self) -> None:
        self.completed = True
        self.rolled_back = True


def _uow_factory(uow: FakeUnitOfWork):
    @asynccontextmanager
    async def context():
        try:
            yield uow
        finally:
            if not uow.completed:
                await uow.rollback()

    return context


def _requirement(**overrides):
    values = {
        "id": "req_1",
        "title": "Offline mode",
        "description": "Support local capture",
        "priority": "high",
        "category": "Feature",
        "source_quote": "Need offline mode",
        "status": "CONFIRMED",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_list_pending_requirements_uses_uow_store_and_closes_read_context():
    uow = FakeUnitOfWork()
    uow.requirements.list_all = AsyncMock(
        return_value=([_requirement(id="req_1")], 3),
    )

    result, total, total_pages = await RequirementReadQueryUseCase(
        uow_factory=_uow_factory(uow),
    ).list_pending_requirements(page=2, page_size=1)

    uow.requirements.list_all.assert_awaited_once_with(
        status="PENDING",
        skip=1,
        limit=1,
    )
    assert result[0]["id"] == "req_1"
    assert total == 3
    assert total_pages == 3
    assert uow.rolled_back is True


@pytest.mark.asyncio
async def test_get_confirmed_requirements_uses_uow_store_projection():
    uow = FakeUnitOfWork()
    uow.requirements.list_all = AsyncMock(return_value=([_requirement()], 1))

    result = await RequirementReadQueryUseCase(
        uow_factory=_uow_factory(uow),
    ).get_confirmed_requirements()

    uow.requirements.list_all.assert_awaited_once_with(
        status="CONFIRMED",
        limit=1000,
    )
    assert result == [
        {
            "id": "req_1",
            "title": "Offline mode",
            "description": "Support local capture",
            "priority": "high",
            "category": "Feature",
            "source_quote": "Need offline mode",
            "status": "CONFIRMED",
        }
    ]
    assert uow.rolled_back is True


@pytest.mark.asyncio
async def test_get_requirement_and_meeting_use_uow_stores():
    uow = FakeUnitOfWork()
    requirement = _requirement()
    meeting = SimpleNamespace(id="mtg_1")
    uow.requirements.get_by_id = AsyncMock(return_value=requirement)
    uow.meetings.get_by_id = AsyncMock(return_value=meeting)

    use_case = RequirementReadQueryUseCase(uow_factory=_uow_factory(uow))

    assert await use_case.get_requirement("req_1") is requirement
    assert await use_case.get_meeting("mtg_1") is meeting
    uow.requirements.get_by_id.assert_awaited_once_with("req_1")
    uow.meetings.get_by_id.assert_awaited_once_with("mtg_1")


@pytest.mark.asyncio
async def test_list_open_questions_with_uow_supports_legacy_session_adapter():
    uow = FakeUnitOfWork()
    questions = [SimpleNamespace(id="qst_1")]
    uow.questions.list_open = AsyncMock(return_value=questions)

    result = await RequirementReadQueryUseCase(
        uow_factory=_uow_factory(FakeUnitOfWork()),
    ).list_open_questions_with_uow(uow, limit=10)

    assert result is questions
    uow.questions.list_open.assert_awaited_once_with(limit=10)
    assert uow.rolled_back is False
