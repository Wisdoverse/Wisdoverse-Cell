from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.export_use_cases import ExportUseCase
from agents.requirement_manager.core.generator import (
    PRDGenerationResult,
    QuestionExportResult,
)


def _requirement():
    return SimpleNamespace(
        id="req_1",
        title="Launch sequencing",
        description="Choose first launch market.",
        category="Feature",
        priority="high",
        status="confirmed",
        source_quote="Launch market was not specified.",
        confirmed_by="pm",
        confirmed_at=datetime.now(UTC),
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
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_export_prd_fetches_filtered_requirements_and_generates_document():
    requirement_repo = MagicMock()
    requirement_repo.list_all = AsyncMock(return_value=([_requirement()], 1))
    question_repo = MagicMock()
    generator = MagicMock()
    generator.generate_prd = AsyncMock(
        return_value=PRDGenerationResult(
            content="# PRD",
            generated_at=datetime.now(UTC),
            requirements_count=1,
            version="2.0",
        )
    )

    result = await ExportUseCase(
        requirement_repository=requirement_repo,
        question_repository=question_repo,
        generator=generator,
    ).export_prd(
        status="confirmed",
        project_name="Wisdoverse Cell",
        version="2.0",
    )

    requirement_repo.list_all.assert_awaited_once_with(
        status="confirmed",
        limit=500,
    )
    generator.generate_prd.assert_awaited_once()
    generated_requirements = generator.generate_prd.call_args.kwargs["requirements"]
    assert generated_requirements[0]["id"] == "req_1"
    assert generated_requirements[0]["confirmed_at"] is not None
    assert result.requirements_count == 1


@pytest.mark.asyncio
async def test_export_questions_fetches_status_and_requirement_titles():
    requirement_repo = MagicMock()
    requirement_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(title="Launch"))
    question_repo = MagicMock()
    question_repo.list_answered = AsyncMock(return_value=[_question()])
    question_repo.list_open = AsyncMock()
    question_repo.list_all = AsyncMock()
    generator = MagicMock()
    generator.generate_questions_export = MagicMock(
        return_value=QuestionExportResult(
            content="Questions",
            generated_at=datetime.now(UTC),
            questions_count=1,
        )
    )

    result = await ExportUseCase(
        requirement_repository=requirement_repo,
        question_repository=question_repo,
        generator=generator,
    ).export_questions(status="answered")

    question_repo.list_answered.assert_awaited_once_with(limit=200)
    question_repo.list_open.assert_not_called()
    question_repo.list_all.assert_not_called()
    requirement_repo.get_by_id.assert_awaited_once_with("req_1")
    exported_questions = generator.generate_questions_export.call_args.kwargs[
        "questions"
    ]
    assert exported_questions[0]["requirement_title"] == "Launch"
    assert result.questions_count == 1
