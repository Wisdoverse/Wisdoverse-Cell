"""Requirement mutation side-effect use case tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.mutation_side_effect_use_cases import (
    RequirementMutationSideEffectUseCase,
)
from agents.requirement_manager.core.requirement_mutation_workflow import (
    RequirementMutationResult,
)
from shared.schemas.event import Event, EventTypes


def _event():
    return Event(
        event_type=EventTypes.REQUIREMENT_DELETED,
        source_agent="requirement-manager",
        payload={"requirement_id": "req_1"},
    )


@pytest.mark.asyncio
async def test_publish_mutation_side_effects_deletes_vector_and_publishes_event():
    vector_index = SimpleNamespace(delete_requirement=AsyncMock())
    event_publisher = SimpleNamespace(publish_staged_event=AsyncMock(return_value=True))
    event = _event()

    await RequirementMutationSideEffectUseCase(
        vector_index=vector_index,
        event_publisher=event_publisher,
    ).publish_requirement_mutation_side_effects(
        RequirementMutationResult(
            entity=object(),
            event=event,
            requirement_id="req_1",
            delete_vector_requirement_id="req_1",
        ),
    )

    vector_index.delete_requirement.assert_awaited_once_with("req_1")
    event_publisher.publish_staged_event.assert_awaited_once_with(
        event,
        requirement_id="req_1",
    )


@pytest.mark.asyncio
async def test_vector_delete_failure_does_not_block_event_publish():
    vector_index = SimpleNamespace(
        delete_requirement=AsyncMock(side_effect=RuntimeError("index down")),
    )
    event_publisher = SimpleNamespace(publish_staged_event=AsyncMock(return_value=True))
    event = _event()

    await RequirementMutationSideEffectUseCase(
        vector_index=vector_index,
        event_publisher=event_publisher,
    ).publish_requirement_mutation_side_effects(
        RequirementMutationResult(
            entity=object(),
            event=event,
            requirement_id="req_1",
            delete_vector_requirement_id="req_1",
        ),
    )

    event_publisher.publish_staged_event.assert_awaited_once_with(
        event,
        requirement_id="req_1",
    )


@pytest.mark.asyncio
async def test_empty_mutation_result_has_no_external_side_effects():
    vector_index = SimpleNamespace(delete_requirement=AsyncMock())
    event_publisher = SimpleNamespace(publish_staged_event=AsyncMock())

    await RequirementMutationSideEffectUseCase(
        vector_index=vector_index,
        event_publisher=event_publisher,
    ).publish_requirement_mutation_side_effects(
        RequirementMutationResult(entity=None),
    )

    vector_index.delete_requirement.assert_not_awaited()
    event_publisher.publish_staged_event.assert_not_awaited()
