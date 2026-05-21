from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.event_use_cases import (
    SUBSCRIBED_EVENTS,
    RequirementManagerEventUseCase,
)
from shared.schemas.event import Event, EventTypes


class FakeUnitOfWork:
    def __init__(self):
        self.completed = False
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.completed = True
        self.committed = True

    async def rollback(self):
        self.completed = True
        self.rolled_back = True


def _uow_factory(uow):
    @asynccontextmanager
    async def uow_context():
        try:
            yield uow
        finally:
            if not uow.completed:
                await uow.rollback()

    return uow_context


def _use_case(
    *,
    agent: AsyncMock | None = None,
    uow: FakeUnitOfWork | None = None,
) -> RequirementManagerEventUseCase:
    if agent is None:
        agent = AsyncMock()
        agent.ingest_meeting_with_uow = AsyncMock(
            return_value=SimpleNamespace(
                requirements_extracted=2,
                questions_generated=1,
            )
        )
        agent.publish_ingest_side_effects = AsyncMock()
    if uow is None:
        uow = FakeUnitOfWork()

    return RequirementManagerEventUseCase(
        agent=agent,
        uow_factory=_uow_factory(uow),
    )


def test_subscribed_events_match_requirement_manager_contract() -> None:
    assert SUBSCRIBED_EVENTS == [
        EventTypes.PROJECT_CREATED,
        EventTypes.PROJECT_UPDATED,
        EventTypes.SPRINT_STARTED,
        EventTypes.SPRINT_COMPLETED,
        EventTypes.MEETING_UPLOADED,
        EventTypes.COORDINATOR_DISPATCH,
    ]


@pytest.mark.asyncio
async def test_meeting_uploaded_ingests_content_with_unit_of_work() -> None:
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(
        return_value=SimpleNamespace(
            requirements_extracted=2,
            questions_generated=1,
        )
    )
    agent.publish_ingest_side_effects = AsyncMock()
    uow = FakeUnitOfWork()
    event = Event.create(
        event_type=EventTypes.MEETING_UPLOADED,
        source_agent="feishu-adapter",
        payload={
            "content": "Meeting summary",
            "source": "feishu",
            "title": "Planning",
            "meeting_date": "2026-05-18T10:00:00Z",
            "participants": ["Alice"],
        },
    )

    result = await _use_case(agent=agent, uow=uow).handle(event)

    assert result == []
    assert uow.committed is True
    agent.ingest_meeting_with_uow.assert_awaited_once_with(
        content="Meeting summary",
        source="feishu",
        uow=uow,
        title="Planning",
        meeting_date=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        participants=["Alice"],
    )
    agent.publish_ingest_side_effects.assert_awaited_once()


@pytest.mark.asyncio
async def test_meeting_uploaded_missing_content_does_not_open_session() -> None:
    opened = False

    @asynccontextmanager
    async def uow_context():
        nonlocal opened
        opened = True
        yield FakeUnitOfWork()

    agent = AsyncMock()
    event = Event.create(
        event_type=EventTypes.MEETING_UPLOADED,
        source_agent="feishu-adapter",
        payload={"title": "Planning"},
    )

    result = await RequirementManagerEventUseCase(
        agent=agent,
        uow_factory=uow_context,
    ).handle(event)

    assert result == []
    assert opened is False
    agent.ingest_meeting_with_uow.assert_not_called()


@pytest.mark.asyncio
async def test_meeting_uploaded_ingest_error_is_swallowed_like_existing_contract() -> None:
    agent = AsyncMock()
    agent.ingest_meeting_with_uow = AsyncMock(side_effect=RuntimeError("extractor down"))
    agent.publish_ingest_side_effects = AsyncMock()
    event = Event.create(
        event_type=EventTypes.MEETING_UPLOADED,
        source_agent="feishu-adapter",
        payload={"content": "Meeting summary"},
    )

    result = await _use_case(agent=agent).handle(event)

    assert result == []
    agent.ingest_meeting_with_uow.assert_awaited_once()
    agent.publish_ingest_side_effects.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_and_sprint_events_return_no_events() -> None:
    use_case = _use_case()
    events = [
        Event.create(
            event_type=EventTypes.PROJECT_CREATED,
            source_agent="project-service",
            payload={"project_id": "proj_1", "name": "Project", "keywords": ["api"]},
        ),
        Event.create(
            event_type=EventTypes.PROJECT_UPDATED,
            source_agent="project-service",
            payload={"project_id": "proj_1", "changes": {"name": "New"}},
        ),
        Event.create(
            event_type=EventTypes.SPRINT_STARTED,
            source_agent="project-service",
            payload={"sprint_id": "spr_1", "requirement_ids": ["req_1"]},
        ),
        Event.create(
            event_type=EventTypes.SPRINT_COMPLETED,
            source_agent="project-service",
            payload={
                "sprint_id": "spr_1",
                "completed_requirement_ids": ["req_1"],
                "incomplete_requirement_ids": [],
            },
        ),
    ]

    for event in events:
        assert await use_case.handle(event) == []


@pytest.mark.asyncio
async def test_coordinator_dispatch_and_unknown_events_return_no_events() -> None:
    use_case = _use_case()

    coordinator_result = await use_case.handle(
        Event.create(
            event_type=EventTypes.COORDINATOR_DISPATCH,
            source_agent="coordinator",
            payload={
                "target_agent": "requirement-manager",
                "task_id": "task_1",
                "instruction": "extract",
            },
        )
    )
    unknown_result = await use_case.handle(
        Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={},
        )
    )

    assert coordinator_result == []
    assert unknown_result == []
