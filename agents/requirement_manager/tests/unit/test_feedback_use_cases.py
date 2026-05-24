from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.feedback_use_cases import RequirementFeedbackUseCase
from shared.core.identifiers import OpenQuestionId, RequirementId


class FakeUnitOfWork:
    def __init__(self):
        self.completed = False
        self.committed = False
        self.questions = AsyncMock()

    async def commit(self):
        self.completed = True
        self.committed = True


def _uow_factory(uow):
    @asynccontextmanager
    async def uow_context():
        yield uow

    return uow_context


@pytest.mark.asyncio
async def test_confirm_requirement_commits_uow_and_publishes_side_effects():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    workflow.confirm_requirement = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    await RequirementFeedbackUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    ).confirm_requirement(
        requirement_id="req_1",
        confirmed_by="pm",
    )

    workflow.confirm_requirement.assert_awaited_once_with(
        requirement_id=RequirementId("req_1"),
        confirmed_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_awaited_once_with(
        mutation_result
    )


@pytest.mark.asyncio
async def test_answer_question_commits_uow_without_side_effect_publish():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    workflow.answer_question = AsyncMock(return_value=SimpleNamespace(entity=object()))
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    await RequirementFeedbackUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    ).answer_question(
        "q_1",
        answer="US first",
        answered_by="pm",
    )

    workflow.answer_question.assert_awaited_once_with(
        OpenQuestionId("q_1"),
        answer="US first",
        answered_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_confirm_returns_summary():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    workflow.batch_confirm_requirements = AsyncMock(
        return_value=(
            [
                {"requirement_id": "req_1", "success": True},
                {"requirement_id": "req_2", "success": False, "error": "missing"},
            ],
            [mutation_result],
        )
    )
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await RequirementFeedbackUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    ).batch_confirm_requirements(
        requirement_ids=["req_1", "req_2"],
        confirmed_by="pm",
    )

    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.results[1]["error"] == "missing"
    assert uow.committed is True
    workflow.batch_confirm_requirements.assert_awaited_once_with(
        requirement_ids=[RequirementId("req_1"), RequirementId("req_2")],
        confirmed_by="pm",
        uow=uow,
    )
    side_effects.publish_requirement_mutation_side_effects.assert_awaited_once_with(
        mutation_result
    )
