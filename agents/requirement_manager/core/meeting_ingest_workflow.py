"""Application workflow for Requirement meeting ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models import Meeting, OpenQuestion, Requirement
from .requirement_mutation_workflow import REQUIREMENT_MANAGER_AGENT_ID
from .unit_of_work_ports import RequirementUnitOfWork

logger = get_logger("requirement_manager.ingest")


@dataclass
class IngestResult:
    """Meeting ingestion result."""

    meeting_id: str
    requirements_extracted: int
    questions_generated: int
    requirement_ids: list[str]
    requirements: list[Requirement] = field(default_factory=list, repr=False)
    open_questions: list[OpenQuestion] = field(default_factory=list, repr=False)
    staged_events: list[Event] = field(default_factory=list, repr=False)


class RequirementExtractorPort(Protocol):
    """Requirement extraction boundary used by the ingestion workflow."""

    async def extract(
        self,
        *,
        content: str,
        source: str,
        meeting_date: str | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
    ) -> Any:
        """Extract structured requirements and questions from meeting content."""


class RequirementVectorIndexPort(Protocol):
    """Search index boundary used for best-effort requirement indexing."""

    async def add_requirements_batch(self, requirements: list[dict[str, Any]]) -> None:
        """Index extracted requirements for semantic search."""


class RequirementMeetingIngestWorkflow:
    """Ingest meeting content into Requirement aggregates inside one UOW."""

    def __init__(
        self,
        *,
        extractor: RequirementExtractorPort,
        vector_index: RequirementVectorIndexPort,
    ) -> None:
        self._extractor = extractor
        self._vector_index = vector_index

    async def ingest_meeting(
        self,
        *,
        content: str,
        source: str,
        uow: RequirementUnitOfWork,
        title: str | None = None,
        meeting_date: datetime | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
        source_id: str | None = None,
    ) -> IngestResult:
        meeting = Meeting(
            source=source,
            source_id=source_id,
            title=title,
            raw_content=content,
            meeting_date=meeting_date,
            participants=participants or [],
            context=context,
        )
        await uow.meetings.create(meeting)

        logger.info(
            "meeting_created",
            meeting_id=meeting.id,
            source=source,
            content_length=len(content),
        )

        extraction = await self._extractor.extract(
            content=content,
            source=source,
            meeting_date=meeting_date.isoformat() if meeting_date else None,
            participants=participants,
            context=context,
        )

        requirements = [
            Requirement(
                title=requirement.title,
                description=requirement.description,
                category=requirement.category,
                priority=requirement.priority,
                source_quote=requirement.source_quote,
                source_meeting_ids=[meeting.id],
            )
            for requirement in extraction.requirements
        ]

        if requirements:
            await uow.requirements.create_batch(requirements)
            await self._index_requirements(meeting.id, requirements)

        questions = []
        requirement_id = requirements[0].id if requirements else None
        if requirement_id:
            questions = [
                OpenQuestion(
                    requirement_id=requirement_id,
                    question=question.question,
                    context=question.context,
                )
                for question in extraction.open_questions
            ]
            if questions:
                await uow.questions.create_batch(questions)

        await uow.meetings.mark_processed(meeting.id)

        extracted_event = None
        if requirements:
            extracted_event = create_requirements_extracted_event(
                requirements=requirements,
                meeting_id=meeting.id,
            )
            await uow.outbox.stage(extracted_event)

        return IngestResult(
            meeting_id=meeting.id,
            requirements_extracted=len(requirements),
            questions_generated=len(questions),
            requirement_ids=[requirement.id for requirement in requirements],
            requirements=requirements,
            open_questions=questions,
            staged_events=[extracted_event] if extracted_event else [],
        )

    async def _index_requirements(
        self,
        meeting_id: str,
        requirements: list[Requirement],
    ) -> None:
        try:
            await self._vector_index.add_requirements_batch(
                [
                    {
                        "id": requirement.id,
                        "title": requirement.title,
                        "description": requirement.description,
                        "category": requirement.category,
                        "metadata": {
                            "meeting_id": meeting_id,
                            "priority": requirement.priority,
                        },
                    }
                    for requirement in requirements
                ],
            )
        except Exception as exc:
            logger.warning(
                "vector_store_batch_add_failed",
                meeting_id=meeting_id,
                count=len(requirements),
                error=str(exc),
            )


def create_requirements_extracted_event(
    *,
    requirements: list[Requirement],
    meeting_id: str,
) -> Event:
    """Create the Requirement extracted integration event."""
    return Event(
        event_type=EventTypes.REQUIREMENT_EXTRACTED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload={
            "meeting_id": meeting_id,
            "requirement_ids": [requirement.id for requirement in requirements],
            "count": len(requirements),
            "requirements": [
                {
                    "id": requirement.id,
                    "title": requirement.title,
                    "priority": requirement.priority,
                    "category": requirement.category,
                }
                for requirement in requirements
            ],
        },
    )
