"""Requirement agent read use case tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.agent_read_use_cases import (
    RequirementAgentReadUseCase,
)
from shared.core.identifiers import MeetingId, RequirementId


def _requirement(**overrides):
    values = {
        "id": "req_1",
        "title": "Offline mode",
        "description": "Support local capture",
        "priority": "high",
        "category": "功能",
        "source_quote": "Users need to work offline",
        "status": "confirmed",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(requirements=None, meetings=None, questions=None):
    return RequirementAgentReadUseCase(
        requirements=requirements or AsyncMock(),
        meetings=meetings or AsyncMock(),
        questions=questions or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_list_pending_requirements_returns_agent_projection_page():
    requirements = AsyncMock()
    requirements.list_all = AsyncMock(
        return_value=([_requirement(id="req_1"), _requirement(id="req_2")], 7),
    )

    result, total, total_pages = await _service(
        requirements=requirements,
    ).list_pending_requirements(page=2, page_size=2)

    requirements.list_all.assert_awaited_once_with(
        status="PENDING",
        skip=2,
        limit=2,
    )
    assert total == 7
    assert total_pages == 4
    assert result == [
        {
            "id": "req_1",
            "title": "Offline mode",
            "description": "Support local capture",
            "priority": "high",
            "category": "功能",
        },
        {
            "id": "req_2",
            "title": "Offline mode",
            "description": "Support local capture",
            "priority": "high",
            "category": "功能",
        },
    ]


@pytest.mark.asyncio
async def test_list_pending_requirements_keeps_empty_result_single_page():
    requirements = AsyncMock()
    requirements.list_all = AsyncMock(return_value=([], 0))

    result, total, total_pages = await _service(
        requirements=requirements,
    ).list_pending_requirements()

    assert result == []
    assert total == 0
    assert total_pages == 1


@pytest.mark.asyncio
async def test_get_confirmed_requirements_returns_export_projection():
    requirements = AsyncMock()
    requirements.list_all = AsyncMock(return_value=([_requirement()], 1))

    result = await _service(requirements=requirements).get_confirmed_requirements()

    requirements.list_all.assert_awaited_once_with(
        status="CONFIRMED",
        limit=1000,
    )
    assert result == [
        {
            "id": "req_1",
            "title": "Offline mode",
            "description": "Support local capture",
            "priority": "high",
            "category": "功能",
            "source_quote": "Users need to work offline",
            "status": "confirmed",
        },
    ]


@pytest.mark.asyncio
async def test_get_requirement_and_meeting_delegate_to_ports():
    requirement = _requirement()
    meeting = SimpleNamespace(id="mtg_1")
    requirements = AsyncMock()
    requirements.get_by_id = AsyncMock(return_value=requirement)
    meetings = AsyncMock()
    meetings.get_by_id = AsyncMock(return_value=meeting)
    service = _service(requirements=requirements, meetings=meetings)

    assert await service.get_requirement(RequirementId("req_1")) is requirement
    assert await service.get_meeting(MeetingId("mtg_1")) is meeting
    requirements.get_by_id.assert_awaited_once_with(RequirementId("req_1"))
    meetings.get_by_id.assert_awaited_once_with(MeetingId("mtg_1"))


@pytest.mark.asyncio
async def test_list_open_questions_delegates_to_question_port():
    questions = AsyncMock()
    open_questions = [SimpleNamespace(id="q_1")]
    questions.list_open = AsyncMock(return_value=open_questions)

    result = await _service(questions=questions).list_open_questions(limit=3)

    assert result is open_questions
    questions.list_open.assert_awaited_once_with(limit=3)
