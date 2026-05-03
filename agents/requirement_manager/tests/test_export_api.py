from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import PlainTextResponse

from agents.requirement_manager.api.export import (
    download_questions,
    export_questions,
)


def _question(**overrides):
    data = {
        "id": "q_1",
        "requirement_id": "req_1",
        "question": "Which market should we launch first?",
        "context": "Launch market was not specified.",
        "status": "answered",
        "answer": "US first.",
        "answered_by": "pm",
        "answered_at": datetime.now(UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_export_questions_supports_answered_status():
    question = _question()
    requirement = SimpleNamespace(title="Launch sequencing")

    with patch("agents.requirement_manager.api.export.QuestionRepository") as q_repo_cls, \
        patch("agents.requirement_manager.api.export.RequirementRepository") as req_repo_cls:
        q_repo = q_repo_cls.return_value
        q_repo.list_answered = AsyncMock(return_value=[question])
        q_repo.list_open = AsyncMock()
        q_repo.list_all = AsyncMock()

        req_repo = req_repo_cls.return_value
        req_repo.get_by_id = AsyncMock(return_value=requirement)

        result = await export_questions(
            status="answered",
            format="json",
            project_name="Wisdoverse Cell",
            session=MagicMock(),
        )

    q_repo.list_answered.assert_awaited_once_with(limit=200)
    q_repo.list_open.assert_not_called()
    q_repo.list_all.assert_not_called()
    req_repo.get_by_id.assert_awaited_once_with("req_1")
    assert result.questions_count == 1
    assert "US first." in result.content


@pytest.mark.asyncio
async def test_export_questions_supports_all_status():
    questions = [
        _question(id="q_open", status="open", answer=None, answered_by=None),
        _question(id="q_answered"),
    ]

    with patch("agents.requirement_manager.api.export.QuestionRepository") as q_repo_cls, \
        patch("agents.requirement_manager.api.export.RequirementRepository") as req_repo_cls:
        q_repo = q_repo_cls.return_value
        q_repo.list_answered = AsyncMock()
        q_repo.list_open = AsyncMock()
        q_repo.list_all = AsyncMock(return_value=questions)

        req_repo = req_repo_cls.return_value
        req_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(title="Requirement"))

        result = await export_questions(
            status="all",
            format="json",
            project_name="Wisdoverse Cell",
            session=MagicMock(),
        )

    q_repo.list_all.assert_awaited_once_with(limit=200)
    q_repo.list_open.assert_not_called()
    q_repo.list_answered.assert_not_called()
    assert result.questions_count == 2


@pytest.mark.asyncio
async def test_download_questions_supports_answered_status():
    question = _question()

    with patch("agents.requirement_manager.api.export.QuestionRepository") as q_repo_cls, \
        patch("agents.requirement_manager.api.export.RequirementRepository") as req_repo_cls:
        q_repo = q_repo_cls.return_value
        q_repo.list_answered = AsyncMock(return_value=[question])
        q_repo.list_open = AsyncMock()

        req_repo = req_repo_cls.return_value
        req_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(title="Requirement"))

        response = await download_questions(
            status="answered",
            project_name="Wisdoverse Cell",
            session=MagicMock(),
        )

    q_repo.list_answered.assert_awaited_once_with(limit=200)
    q_repo.list_open.assert_not_called()
    assert isinstance(response, PlainTextResponse)
    assert "US first." in response.body.decode("utf-8")
