from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.api.requirements import (
    delete_requirement,
    update_requirement,
)
from agents.requirement_manager.api.schemas import (
    DeleteRequirementRequest,
    RequirementUpdateRequest,
)


def _requirement():
    now = datetime.now(UTC)
    requirement = MagicMock()
    requirement.id = "req_1"
    requirement.title = "Updated requirement"
    requirement.description = "Updated description"
    requirement.status = "pending"
    requirement.priority = "high"
    requirement.category = "Feature"
    requirement.source_quote = None
    requirement.source_meeting_ids = []
    requirement.confirmed_by = None
    requirement.confirmed_at = None
    requirement.open_questions = []
    requirement.history = []
    requirement.created_at = now
    requirement.updated_at = now
    return requirement


@pytest.mark.asyncio
async def test_update_requirement_route_delegates_to_mutation_use_case():
    mutations = MagicMock()
    mutations.update_requirement = AsyncMock(return_value=_requirement())

    result = await update_requirement(
        "req_1",
        RequirementUpdateRequest(title="Updated requirement", comment="pm"),
        mutations=mutations,
    )

    assert result.id == "req_1"
    mutations.update_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        changes={"title": "Updated requirement", "comment": "pm"},
    )


@pytest.mark.asyncio
async def test_delete_requirement_route_delegates_to_mutation_use_case():
    mutations = MagicMock()
    mutations.delete_requirement = AsyncMock(return_value=_requirement())

    result = await delete_requirement(
        "req_1",
        DeleteRequirementRequest(deleted_by="pm"),
        mutations=mutations,
    )

    assert result.requirement_id == "req_1"
    assert result.title == "Updated requirement"
    mutations.delete_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        deleted_by="pm",
    )
