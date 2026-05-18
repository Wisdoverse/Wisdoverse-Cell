"""Application use cases for meeting ingestion."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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


class MeetingDedupRepository(Protocol):
    async def get_by_source_id(self, source: str, source_id: str) -> object | None:
        """Return an existing meeting by source-system identity."""


class MeetingIngestAgent(Protocol):
    async def ingest_meeting(
        self,
        *,
        content: str,
        source: str,
        session: object,
        title: str | None = None,
        meeting_date: datetime | None = None,
        participants: list[str] | None = None,
        context: str | None = None,
        source_id: str | None = None,
    ) -> object:
        """Ingest a meeting and extract requirements."""


class IngestUseCase:
    """Application use case for upload and Feishu meeting ingestion."""

    def __init__(
        self,
        *,
        meeting_repository: MeetingDedupRepository,
        agent: MeetingIngestAgent,
        session: object,
    ):
        self._meetings = meeting_repository
        self._agent = agent
        self._session = session

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
        result = await self._agent.ingest_meeting(
            content=content,
            source=source,
            session=self._session,
            title=title,
            meeting_date=_parse_optional_datetime(meeting_date),
            participants=participants,
            context=context,
        )
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
        if meeting_id:
            existing = await self._meetings.get_by_source_id("feishu", meeting_id)
            if existing:
                return IngestUseCaseResult(
                    meeting_id=existing.id,
                    requirements_extracted=0,
                    questions_generated=0,
                    deduplicated=True,
                )

        result = await self._agent.ingest_meeting(
            content=summary,
            source="feishu",
            session=self._session,
            title=topic,
            meeting_date=_parse_optional_datetime(meeting_time),
            participants=participants,
            source_id=meeting_id,
        )
        return IngestUseCaseResult.from_agent_result(result)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
