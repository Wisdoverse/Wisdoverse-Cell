"""Application use cases for Requirement Manager direct agent requests."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory


class RequirementRequestIngestAgent(Protocol):
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
        """Ingest a meeting through the runtime agent boundary."""

    async def publish_ingest_side_effects(self, result: object) -> None:
        """Publish post-commit side effects for a completed ingestion."""


class RequirementManagerRequestUseCase:
    """Dispatch Requirement Manager agent requests outside the service shell."""

    def __init__(
        self,
        *,
        agent: RequirementRequestIngestAgent,
        uow_factory: RequirementUnitOfWorkFactory,
    ) -> None:
        self._agent = agent
        self._uow_factory = uow_factory

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "ingest":
            return await self._ingest(request)
        return {"status": "ok"}

    async def _ingest(self, request: dict[str, Any]) -> dict[str, Any]:
        content = request.get("content")
        if not isinstance(content, str) or not content.strip():
            return {"status": "error", "error": "content_required"}

        try:
            meeting_date = self._parse_meeting_date(request.get("meeting_date"))
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}

        async with self._uow_factory() as uow:
            result = await self._agent.ingest_meeting_with_uow(
                content=content,
                source=str(request.get("source") or "agent_request"),
                uow=uow,
                title=self._optional_str(request.get("title")),
                meeting_date=meeting_date,
                participants=self._string_list(request.get("participants")),
                context=self._optional_str(request.get("context")),
                source_id=self._optional_str(request.get("source_id")),
            )
            await uow.commit()

        await self._agent.publish_ingest_side_effects(result)

        return {
            "status": "ok",
            "meeting_id": result.meeting_id,
            "requirements_extracted": result.requirements_extracted,
            "questions_generated": result.questions_generated,
            "requirement_ids": result.requirement_ids,
        }

    @staticmethod
    def _parse_meeting_date(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("meeting_date_must_be_iso_datetime")

        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("meeting_date_must_be_iso_datetime") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]
