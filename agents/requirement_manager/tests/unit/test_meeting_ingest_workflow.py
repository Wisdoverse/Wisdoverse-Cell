"""Requirement meeting ingestion workflow tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.meeting_ingest_workflow import (
    RequirementMeetingIngestWorkflow,
    create_requirements_extracted_event,
)
from shared.schemas.event import EventTypes


def _extracted_requirement(**overrides):
    values = {
        "title": "Offline capture",
        "description": "Capture notes without connectivity",
        "category": "功能",
        "priority": "high",
        "source_quote": "We need offline mode",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _extracted_question(**overrides):
    values = {
        "question": "Which platforms need offline mode?",
        "context": "Scope is unclear",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeMeetingStore:
    def __init__(self):
        self.created = []
        self.processed: list[str] = []

    async def create(self, meeting):
        meeting.id = "mtg_1"
        self.created.append(meeting)
        return meeting

    async def mark_processed(self, meeting_id: str):
        self.processed.append(meeting_id)


class FakeRequirementStore:
    def __init__(self):
        self.created = []

    async def create_batch(self, requirements):
        for index, requirement in enumerate(requirements, start=1):
            requirement.id = f"req_{index}"
        self.created.extend(requirements)
        return requirements


class FakeQuestionStore:
    def __init__(self):
        self.created = []

    async def create_batch(self, questions):
        self.created.extend(questions)
        return questions


class FakeOutbox:
    def __init__(self):
        self.staged = []

    async def stage(self, event):
        self.staged.append(event)


def _uow():
    return SimpleNamespace(
        meetings=FakeMeetingStore(),
        requirements=FakeRequirementStore(),
        questions=FakeQuestionStore(),
        outbox=FakeOutbox(),
    )


@pytest.mark.asyncio
async def test_ingest_meeting_persists_requirements_questions_index_and_event():
    extractor = AsyncMock()
    extractor.extract = AsyncMock(
        return_value=SimpleNamespace(
            requirements=[_extracted_requirement(), _extracted_requirement(title="Sync")],
            open_questions=[_extracted_question()],
        ),
    )
    vector_index = AsyncMock()
    vector_index.add_requirements_batch = AsyncMock()
    uow = _uow()

    result = await RequirementMeetingIngestWorkflow(
        extractor=extractor,
        vector_index=vector_index,
    ).ingest_meeting(
        content="Meeting notes",
        source="upload",
        uow=uow,
        title="Planning",
        meeting_date=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        participants=["Alice"],
        context="Sprint planning",
        source_id="src_1",
    )

    meeting = uow.meetings.created[0]
    assert meeting.id == "mtg_1"
    assert meeting.title == "Planning"
    assert meeting.participants == ["Alice"]
    assert result.meeting_id == "mtg_1"
    assert result.requirement_ids == ["req_1", "req_2"]
    assert result.requirements_extracted == 2
    assert result.questions_generated == 1
    assert uow.meetings.processed == ["mtg_1"]
    assert len(uow.requirements.created) == 2
    assert uow.questions.created[0].requirement_id == "req_1"
    assert uow.outbox.staged[0].event_type == EventTypes.REQUIREMENT_EXTRACTED
    vector_index.add_requirements_batch.assert_awaited_once()
    vector_doc = vector_index.add_requirements_batch.await_args.args[0][0]
    assert vector_doc["metadata"] == {"meeting_id": "mtg_1", "priority": "high"}


@pytest.mark.asyncio
async def test_ingest_meeting_without_requirements_skips_index_questions_and_event():
    extractor = AsyncMock()
    extractor.extract = AsyncMock(
        return_value=SimpleNamespace(requirements=[], open_questions=[]),
    )
    vector_index = AsyncMock()
    vector_index.add_requirements_batch = AsyncMock()
    uow = _uow()

    result = await RequirementMeetingIngestWorkflow(
        extractor=extractor,
        vector_index=vector_index,
    ).ingest_meeting(content="Chit chat", source="upload", uow=uow)

    assert result.requirements_extracted == 0
    assert result.questions_generated == 0
    assert result.requirement_ids == []
    assert uow.meetings.processed == ["mtg_1"]
    assert uow.requirements.created == []
    assert uow.questions.created == []
    assert uow.outbox.staged == []
    vector_index.add_requirements_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_vector_index_failure_does_not_block_ingest_transaction():
    extractor = AsyncMock()
    extractor.extract = AsyncMock(
        return_value=SimpleNamespace(
            requirements=[_extracted_requirement()],
            open_questions=[],
        ),
    )
    vector_index = AsyncMock()
    vector_index.add_requirements_batch = AsyncMock(side_effect=RuntimeError("down"))
    uow = _uow()

    result = await RequirementMeetingIngestWorkflow(
        extractor=extractor,
        vector_index=vector_index,
    ).ingest_meeting(content="Meeting notes", source="upload", uow=uow)

    assert result.requirement_ids == ["req_1"]
    assert uow.outbox.staged[0].event_type == EventTypes.REQUIREMENT_EXTRACTED


def test_create_requirements_extracted_event_uses_requirement_contract():
    requirement = SimpleNamespace(
        id="req_1",
        title="Offline capture",
        priority="high",
        category="功能",
    )

    event = create_requirements_extracted_event(
        requirements=[requirement],
        meeting_id="mtg_1",
    )

    assert event.event_type == EventTypes.REQUIREMENT_EXTRACTED
    assert event.source_agent == "requirement-manager"
    assert event.payload["meeting_id"] == "mtg_1"
    assert event.payload["requirement_ids"] == ["req_1"]
