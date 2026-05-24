"""Application workflow for Requirement meeting ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from shared.core.identifiers import MeetingId, RequirementId
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models import Meeting, OpenQuestion, Requirement
from .domain.aggregate_consistency import (
    MEETING,
    OPEN_QUESTION,
    REQUIREMENT,
    REQUIREMENT_EVENT_OUTBOX,
    RequirementAggregateConsistencyPolicy,
)
from .domain.extraction_materialization import (
    RequirementExtractionMaterializer,
    RequirementExtractionPublication,
    RequirementExtractionPublicationPolicy,
)
from .domain.meeting_source import MeetingSourceMetadata
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
        self._extraction_materializer = RequirementExtractionMaterializer()
        self._publication_policy = RequirementExtractionPublicationPolicy()
        self._consistency_policy = RequirementAggregateConsistencyPolicy()

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
        source_metadata = MeetingSourceMetadata.from_values(
            source=source,
            source_id=source_id,
            title=title,
            meeting_date=meeting_date,
            participants=participants,
            context=context,
        )
        meeting = Meeting(**source_metadata.meeting_kwargs(raw_content=content))
        await uow.meetings.create(meeting)

        logger.info(
            "meeting_created",
            meeting_id=meeting.id,
            source=source_metadata.source,
            content_length=len(content),
        )

        extraction = await self._extractor.extract(
            content=content,
            source=source_metadata.source,
            meeting_date=source_metadata.meeting_date_iso(),
            participants=source_metadata.participants_for_extraction(),
            context=source_metadata.context,
        )

        extraction_plan = self._extraction_materializer.materialize(
            extraction=extraction,
            meeting_id=MeetingId(meeting.id),
        )

        requirements = [
            Requirement(**requirement.requirement_kwargs())
            for requirement in extraction_plan.requirements
        ]
        expected_question_count = (
            extraction_plan.open_questions_count if requirements else 0
        )
        consistency_scope = self._consistency_policy.meeting_ingest(
            requirements_count=len(requirements),
            open_questions_count=expected_question_count,
        )
        consistency_scope.assert_allows_same_transaction(
            _meeting_ingest_write_set(
                requirements_count=len(requirements),
                open_questions_count=expected_question_count,
            )
        )

        publication: RequirementExtractionPublication | None = None
        if requirements:
            await uow.requirements.create_batch(requirements)
            publication = self._publication_policy.build(
                meeting_id=MeetingId(meeting.id),
                requirements=requirements,
            )
            await self._index_requirements(publication)

        questions = []
        if requirements:
            question_drafts = extraction_plan.materialize_open_questions(
                requirement_ids=[
                    RequirementId(requirement.id) for requirement in requirements
                ],
            )
            questions = [
                OpenQuestion(**question.open_question_kwargs())
                for question in question_drafts
            ]
            if questions:
                await uow.questions.create_batch(questions)

        await uow.meetings.mark_processed(MeetingId(meeting.id))

        extracted_event = None
        if publication:
            extracted_event = create_requirements_extracted_event(
                publication=publication,
            )
            await uow.outbox.stage(extracted_event)

        return IngestResult(
            meeting_id=meeting.id,
            requirements_extracted=len(requirements),
            questions_generated=len(questions),
            requirement_ids=list(publication.requirement_ids) if publication else [],
            requirements=requirements,
            open_questions=questions,
            staged_events=[extracted_event] if extracted_event else [],
        )

    async def _index_requirements(
        self,
        publication: RequirementExtractionPublication,
    ) -> None:
        try:
            await self._vector_index.add_requirements_batch(
                publication.search_index_documents(),
            )
        except Exception as exc:
            logger.warning(
                "vector_store_batch_add_failed",
                meeting_id=str(publication.meeting_id),
                count=publication.count,
                error=str(exc),
            )


def create_requirements_extracted_event(
    *,
    publication: RequirementExtractionPublication,
) -> Event:
    """Create the Requirement extracted integration event."""
    return Event(
        event_type=EventTypes.REQUIREMENT_EXTRACTED,
        source_agent=REQUIREMENT_MANAGER_AGENT_ID,
        payload=publication.event_payload(),
    )


def _meeting_ingest_write_set(
    *,
    requirements_count: int,
    open_questions_count: int,
) -> tuple[str, ...]:
    aggregates = [MEETING]
    if requirements_count:
        aggregates.extend((REQUIREMENT, REQUIREMENT_EVENT_OUTBOX))
    if open_questions_count:
        aggregates.append(OPEN_QUESTION)
    return tuple(aggregates)
