from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.requirement_mutations import (
    RequirementMutationUseCase,
)


@pytest.mark.asyncio
async def test_update_requirement_delegates_to_agent_with_session():
    agent = AsyncMock()
    agent.update_requirement = AsyncMock(return_value=object())
    session = MagicMock()

    result = await RequirementMutationUseCase(
        agent=agent,
        session=session,
    ).update_requirement(
        requirement_id="req_1",
        changes={"title": "New title"},
    )

    assert result is not None
    agent.update_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        changes={"title": "New title"},
        session=session,
    )


@pytest.mark.asyncio
async def test_delete_requirement_delegates_to_agent_with_session():
    agent = AsyncMock()
    agent.delete_requirement = AsyncMock(return_value=object())
    session = MagicMock()

    result = await RequirementMutationUseCase(
        agent=agent,
        session=session,
    ).delete_requirement(
        requirement_id="req_1",
        deleted_by="pm",
    )

    assert result is not None
    agent.delete_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        deleted_by="pm",
        session=session,
    )
