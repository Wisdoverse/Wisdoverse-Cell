from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.requirement_mutation_workflow import (
    RequirementMutationWorkflow,
)
from shared.schemas.event import EventTypes


def _requirement(**overrides):
    values = {
        "id": "req_1",
        "title": "Original title",
        "description": "Original description",
        "priority": "MEDIUM",
        "category": "feature",
        "add_history": MagicMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _uow():
    return SimpleNamespace(
        requirements=AsyncMock(),
        questions=AsyncMock(),
        feedback=AsyncMock(),
        outbox=SimpleNamespace(stage=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_confirm_requirement_stages_confirmed_event_in_uow():
    uow = _uow()
    requirement = _requirement()
    uow.requirements.confirm = AsyncMock(return_value=requirement)

    result = await RequirementMutationWorkflow().confirm_requirement(
        requirement_id="req_1",
        confirmed_by="pm",
        uow=uow,
    )

    assert result.entity is requirement
    assert result.requirement_id == "req_1"
    assert result.event is not None
    assert result.event.event_type == EventTypes.REQUIREMENT_CONFIRMED
    assert result.event.source_agent == "requirement-manager"
    assert result.event.payload["confirmed_by"] == "pm"
    uow.outbox.stage.assert_awaited_once_with(result.event)


@pytest.mark.asyncio
async def test_update_requirement_records_history_feedback_and_changed_event():
    uow = _uow()
    original = _requirement()
    updated = _requirement(title="Updated title", priority="HIGH")
    uow.requirements.get_by_id = AsyncMock(return_value=original)
    uow.requirements.update = AsyncMock(return_value=updated)
    uow.feedback.create = AsyncMock()

    result = await RequirementMutationWorkflow().update_requirement(
        requirement_id="req_1",
        changes={"title": "Updated title", "priority": "HIGH", "comment": "pm"},
        uow=uow,
    )

    assert result.entity is updated
    original.add_history.assert_called_once()
    uow.feedback.create.assert_awaited_once()
    assert result.event is not None
    assert result.event.event_type == EventTypes.REQUIREMENT_CHANGED
    assert result.event.payload["changed_fields"] == ["title", "priority"]
    assert result.event.payload["changed_by"] == "pm"
    uow.outbox.stage.assert_awaited_once_with(result.event)


@pytest.mark.asyncio
async def test_delete_requirement_defers_vector_delete_until_after_commit():
    uow = _uow()
    requirement = _requirement()
    uow.requirements.delete = AsyncMock(return_value=requirement)

    result = await RequirementMutationWorkflow().delete_requirement(
        requirement_id="req_1",
        deleted_by="pm",
        uow=uow,
    )

    assert result.entity is requirement
    assert result.delete_vector_requirement_id == "req_1"
    assert result.event is not None
    assert result.event.event_type == EventTypes.REQUIREMENT_DELETED
    uow.outbox.stage.assert_awaited_once_with(result.event)
