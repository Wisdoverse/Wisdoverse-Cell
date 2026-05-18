from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import PlainTextResponse

from agents.requirement_manager.api.export import (
    download_questions,
    export_questions,
)
from agents.requirement_manager.core.export_use_cases import ExportUseCase
from agents.requirement_manager.core.generator import QuestionExportResult


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


def _export_use_case(question_repo, requirement_repo, result_content="US first."):
    generator = MagicMock()
    generator.generate_questions_export = MagicMock(
        return_value=QuestionExportResult(
            content=result_content,
            generated_at=datetime.now(UTC),
            questions_count=1,
        )
    )
    return ExportUseCase(
        requirement_repository=requirement_repo,
        question_repository=question_repo,
        generator=generator,
    )


@pytest.mark.asyncio
async def test_export_questions_supports_answered_status():
    question = _question()
    requirement = SimpleNamespace(title="Launch sequencing")
    q_repo = MagicMock()
    q_repo.list_answered = AsyncMock(return_value=[question])
    q_repo.list_open = AsyncMock()
    q_repo.list_all = AsyncMock()
    req_repo = MagicMock()
    req_repo.get_by_id = AsyncMock(return_value=requirement)

    result = await export_questions(
        status="answered",
        format="json",
        project_name="Wisdoverse Cell",
        exports=_export_use_case(q_repo, req_repo),
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
    q_repo = MagicMock()
    q_repo.list_answered = AsyncMock()
    q_repo.list_open = AsyncMock()
    q_repo.list_all = AsyncMock(return_value=questions)
    req_repo = MagicMock()
    req_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(title="Requirement"))
    generator = MagicMock()
    generator.generate_questions_export = MagicMock(
        return_value=QuestionExportResult(
            content="Questions",
            generated_at=datetime.now(UTC),
            questions_count=2,
        )
    )

    result = await export_questions(
        status="all",
        format="json",
        project_name="Wisdoverse Cell",
        exports=ExportUseCase(
            requirement_repository=req_repo,
            question_repository=q_repo,
            generator=generator,
        ),
    )

    q_repo.list_all.assert_awaited_once_with(limit=200)
    q_repo.list_open.assert_not_called()
    q_repo.list_answered.assert_not_called()
    assert result.questions_count == 2


@pytest.mark.asyncio
async def test_download_questions_supports_answered_status():
    question = _question()
    q_repo = MagicMock()
    q_repo.list_answered = AsyncMock(return_value=[question])
    q_repo.list_open = AsyncMock()
    q_repo.list_all = AsyncMock()
    req_repo = MagicMock()
    req_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(title="Requirement"))

    response = await download_questions(
        status="answered",
        project_name="Wisdoverse Cell",
        exports=_export_use_case(q_repo, req_repo),
    )

    q_repo.list_answered.assert_awaited_once_with(limit=200)
    q_repo.list_open.assert_not_called()
    assert isinstance(response, PlainTextResponse)
    assert "US first." in response.body.decode("utf-8")
