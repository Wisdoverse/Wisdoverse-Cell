"""Application use cases for meeting ingestion."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class IngestUseCaseResult:
    """Ingestion result exposed to HTTP adapters."""

    meeting_id: str
    requirements_extracted: int
    questions_generated: int
    deduplicated: bool = False

    @classmethod
    def from_agent_result(cls, result: object) -> "IngestUseCaseResult":
        return cls(
            meeting_id=result.meeting_id,
            requirements_extracted=result.requirements_extracted,
            questions_generated=result.questions_generated,
        )


class MeetingIngestAgent(Protocol):
    async def ingest_meeting_with_uow(
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
    ) -> object:
        """Ingest a meeting and extract requirements."""

    async def publish_ingest_side_effects(self, result: object) -> None:
        """Publish post-commit side effects for a completed ingestion."""


class IngestUseCase:
    """Application use case for upload and Feishu meeting ingestion."""

    def __init__(
        self,
        *,
        agent: MeetingIngestAgent,
        uow_factory: RequirementUnitOfWorkFactory,
    ):
        self._agent = agent
        self._uow_factory = uow_factory

    async def upload_content(
        self,
        *,
        content: str,
        source: str,
        title: str | None = None,
        meeting_date: str | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
    ) -> IngestUseCaseResult:
        async with self._uow_factory() as uow:
            result = await self._agent.ingest_meeting_with_uow(
                content=content,
                source=source,
                uow=uow,
                title=title,
                meeting_date=_parse_optional_datetime(meeting_date),
                participants=participants,
                context=context,
            )
            await uow.commit()

        await self._agent.publish_ingest_side_effects(result)
        return IngestUseCaseResult.from_agent_result(result)

    async def ingest_feishu(
        self,
        *,
        summary: str,
        meeting_id: str | None = None,
        topic: str | None = None,
        participants: list[str] | None = None,
        meeting_time: str | None = None,
    ) -> IngestUseCaseResult:
        async with self._uow_factory() as uow:
            if meeting_id:
                existing = await uow.meetings.get_by_source_id("feishu", meeting_id)
                if existing:
                    return IngestUseCaseResult(
                        meeting_id=existing.id,
                        requirements_extracted=0,
                        questions_generated=0,
                        deduplicated=True,
                    )

            result = await self._agent.ingest_meeting_with_uow(
                content=summary,
                source="feishu",
                uow=uow,
                title=topic,
                meeting_date=_parse_optional_datetime(meeting_time),
                participants=participants,
                source_id=meeting_id,
            )
            await uow.commit()

        await self._agent.publish_ingest_side_effects(result)
        return IngestUseCaseResult.from_agent_result(result)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
