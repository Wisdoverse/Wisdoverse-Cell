"""Requirement command use case tests."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.requirement_command_use_cases import (
    RequirementCommandUseCase,
)


class FakeUnitOfWork:
    def __init__(self):
        self.completed = False
        self.committed = False

    async def commit(self):
        self.completed = True
        self.committed = True


def _uow_factory(uow):
    @asynccontextmanager
    async def context():
        yield uow

    return context


def _use_case(workflow, side_effects, uow):
    return RequirementCommandUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    )


@pytest.mark.asyncio
async def test_confirm_requirement_commits_factory_uow_and_publishes_side_effects():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    entity = object()
    mutation_result = SimpleNamespace(entity=entity)
    workflow.confirm_requirement = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await _use_case(workflow, side_effects, uow).confirm_requirement(
        requirement_id="req_1",
        confirmed_by="pm",
    )

    assert result is entity
    workflow.confirm_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        confirmed_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_awaited_once_with(
        mutation_result,
    )


@pytest.mark.asyncio
async def test_update_requirement_accepts_caller_owned_uow():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    entity = object()
    mutation_result = SimpleNamespace(entity=entity)
    workflow.update_requirement = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    factory_uow = FakeUnitOfWork()
    provided_uow = FakeUnitOfWork()

    result = await _use_case(
        workflow,
        side_effects,
        factory_uow,
    ).update_requirement(
        requirement_id="req_1",
        changes={"title": "Updated"},
        uow=provided_uow,
    )

    assert result is entity
    workflow.update_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        changes={"title": "Updated"},
        uow=provided_uow,
    )
    assert provided_uow.committed is True
    assert factory_uow.committed is False


@pytest.mark.asyncio
async def test_answer_question_commits_without_publishing_side_effects():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    workflow.answer_question = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await _use_case(workflow, side_effects, uow).answer_question(
        "q_1",
        answer="US first",
        answered_by="pm",
    )

    assert result is mutation_result.entity
    workflow.answer_question.assert_awaited_once_with(
        "q_1",
        answer="US first",
        answered_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_reject_commits_and_publishes_each_mutation_result():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result_1 = SimpleNamespace(entity=object())
    mutation_result_2 = SimpleNamespace(entity=object())
    results = [
        {"requirement_id": "req_1", "success": True, "error": None},
        {"requirement_id": "req_2", "success": True, "error": None},
    ]
    workflow.batch_reject_requirements = AsyncMock(
        return_value=(results, [mutation_result_1, mutation_result_2]),
    )
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await _use_case(workflow, side_effects, uow).batch_reject_requirements(
        requirement_ids=["req_1", "req_2"],
        reason="Out of scope",
        rejected_by="pm",
    )

    assert result is results
    assert uow.committed is True
    workflow.batch_reject_requirements.assert_awaited_once_with(
        requirement_ids=["req_1", "req_2"],
        reason="Out of scope",
        rejected_by="pm",
        uow=uow,
    )
    assert side_effects.publish_requirement_mutation_side_effects.await_count == 2
    side_effects.publish_requirement_mutation_side_effects.assert_any_await(
        mutation_result_1,
    )
    side_effects.publish_requirement_mutation_side_effects.assert_any_await(
        mutation_result_2,
    )
