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
    agent = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    agent.update_requirement_with_uow = AsyncMock(return_value=mutation_result)
    agent.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await RequirementMutationUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).update_requirement(
        requirement_id="req_1",
        changes={"title": "New title"},
    )

    assert result is not None
    agent.update_requirement_with_uow.assert_awaited_once_with(
        requirement_id="req_1",
        changes={"title": "New title"},
        uow=uow,
    )
    assert uow.committed is True
    agent.publish_requirement_mutation_side_effects.assert_awaited_once_with(mutation_result)


@pytest.mark.asyncio
async def test_delete_requirement_commits_uow_and_publishes_side_effects():
    agent = AsyncMock()
    mutation_result = SimpleNamespace(entity=object())
    agent.delete_requirement_with_uow = AsyncMock(return_value=mutation_result)
    agent.publish_requirement_mutation_side_effects = AsyncMock()
    uow = FakeUnitOfWork()

    result = await RequirementMutationUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    ).delete_requirement(
        requirement_id="req_1",
        deleted_by="pm",
    )

    assert result is not None
    agent.delete_requirement_with_uow.assert_awaited_once_with(
        requirement_id="req_1",
        deleted_by="pm",
        uow=uow,
    )
    assert uow.committed is True
    agent.publish_requirement_mutation_side_effects.assert_awaited_once_with(mutation_result)
