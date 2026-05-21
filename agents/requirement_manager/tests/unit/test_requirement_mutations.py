from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.requirement_mutations import (
    RequirementMutationUseCase,
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
    async def uow_context():
        yield uow

    return uow_context


@pytest.mark.asyncio
async def test_update_requirement_commits_uow_and_publishes_side_effects():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    workflow.update_requirement = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await RequirementMutationUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    ).update_requirement(
        requirement_id="req_1",
        changes={"title": "New title"},
    )

    assert result is not None
    workflow.update_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        changes={"title": "New title"},
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_awaited_once_with(
        mutation_result
    )


@pytest.mark.asyncio
async def test_delete_requirement_commits_uow_and_publishes_side_effects():
    workflow = AsyncMock()
    side_effects = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    workflow.delete_requirement = AsyncMock(return_value=mutation_result)
    side_effects.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await RequirementMutationUseCase(
        mutation_workflow=workflow,
        side_effects=side_effects,
        uow_factory=_uow_factory(uow),
    ).delete_requirement(
        requirement_id="req_1",
        deleted_by="pm",
    )

    assert result is not None
    workflow.delete_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        deleted_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    side_effects.publish_requirement_mutation_side_effects.assert_awaited_once_with(
        mutation_result
    )
