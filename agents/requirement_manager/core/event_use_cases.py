"""Application use cases for Requirement Manager event orchestration."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

logger = get_logger("requirement-manager.event_use_cases")

SUBSCRIBED_EVENTS = [
    EventTypes.PROJECT_CREATED,
    EventTypes.PROJECT_UPDATED,
    EventTypes.SPRINT_STARTED,
    EventTypes.SPRINT_COMPLETED,
    EventTypes.MEETING_UPLOADED,
    EventTypes.COORDINATOR_DISPATCH,
]


class RequirementEventIngestAgent(Protocol):
    async def ingest_meeting(
        self,
        *,
        content: str,
        source: str,
        session: object,
        title: str | None = None,
        meeting_date: datetime | str | None = None,
        participants: list[str] | None = None,
    ) -> object:
        """Ingest meeting content through the requirement runtime boundary."""


class RequirementManagerEventUseCase:
    """Dispatch Requirement Manager integration events outside the service shell."""

    def __init__(
        self,
        *,
        agent: RequirementEventIngestAgent,
        session_factory: Callable[[], AbstractAsyncContextManager[object]],
    ) -> None:
        self._agent = agent
        self._session_factory = session_factory

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.COORDINATOR_DISPATCH:
            return self._handle_coordinator_dispatch(event)

        handlers = {
            EventTypes.PROJECT_CREATED: self._handle_project_created,
            EventTypes.PROJECT_UPDATED: self._handle_project_updated,
            EventTypes.SPRINT_STARTED: self._handle_sprint_started,
            EventTypes.SPRINT_COMPLETED: self._handle_sprint_completed,
            EventTypes.MEETING_UPLOADED: self._handle_meeting_uploaded,
        }
        handler = handlers.get(event.event_type)
        if handler is None:
            logger.warning(
                "unhandled_event_type",
                event_type=event.event_type,
                event_id=event.event_id,
            )
            return []

        logger.info(
            "handling_event",
            event_type=event.event_type,
            event_id=event.event_id,
            trace_id=event.metadata.trace_id if event.metadata else None,
        )

        try:
            return await handler(event)
        except Exception as exc:
            logger.error(
                "event_handler_failed",
                event_type=event.event_type,
                event_id=event.event_id,
                error=str(exc),
            )
            raise

    def _handle_coordinator_dispatch(self, event: Event) -> list[Event]:
        if event.payload.get("target_agent") == "requirement-manager":
            logger.info(
                "coordinator_dispatch_received",
                task_id=event.payload.get("task_id"),
                workflow_id=event.payload.get("workflow_id"),
                instruction=event.payload.get("instruction"),
            )
        return []

    async def _handle_project_created(self, event: Event) -> list[Event]:
        payload = event.payload
        project_id = payload.get("project_id")
        project_name = payload.get("name", "")
        keywords = payload.get("keywords", [])

        if not project_id:
            logger.warning("project_created_missing_id", event_id=event.event_id)
            return []

        logger.info(
            "project_created_received",
            project_id=project_id,
            project_name=project_name,
            keywords=keywords,
        )
        return []

    async def _handle_project_updated(self, event: Event) -> list[Event]:
        payload = event.payload
        project_id = payload.get("project_id")
        changes = payload.get("changes", {})

        logger.info(
            "project_updated_received",
            project_id=project_id,
            changes=list(changes.keys()),
        )
        return []

    async def _handle_sprint_started(self, event: Event) -> list[Event]:
        payload = event.payload
        sprint_id = payload.get("sprint_id")
        sprint_name = payload.get("name", "")
        requirement_ids = payload.get("requirement_ids", [])
        _ = payload.get("start_date")
        _ = payload.get("end_date")

        logger.info(
            "sprint_started_received",
            sprint_id=sprint_id,
            sprint_name=sprint_name,
            requirement_count=len(requirement_ids),
        )
        return []

    async def _handle_sprint_completed(self, event: Event) -> list[Event]:
        payload = event.payload
        sprint_id = payload.get("sprint_id")
        completed_requirements = payload.get("completed_requirement_ids", [])
        incomplete_requirements = payload.get("incomplete_requirement_ids", [])

        logger.info(
            "sprint_completed_received",
            sprint_id=sprint_id,
            completed_count=len(completed_requirements),
            incomplete_count=len(incomplete_requirements),
        )
        return []

    async def _handle_meeting_uploaded(self, event: Event) -> list[Event]:
        payload = event.payload
        content = payload.get("content")
        source = payload.get("source", "event")
        title = payload.get("title")
        meeting_date = payload.get("meeting_date")
        participants = payload.get("participants", [])

        if not content:
            logger.warning("meeting_uploaded_missing_content", event_id=event.event_id)
            return []

        logger.info(
            "meeting_uploaded_received",
            event_id=event.event_id,
            title_hash=hash_identifier(title),
            title_length=len(str(title or "")),
            content_length=len(content),
        )

        try:
            async with self._session_factory() as session:
                result = await self._agent.ingest_meeting(
                    content=content,
                    source=source,
                    session=session,
                    title=title,
                    meeting_date=meeting_date,
                    participants=participants,
                )

            logger.info(
                "meeting_processed_from_event",
                event_id=event.event_id,
                requirements_count=result.requirements_extracted,
                questions_count=result.questions_generated,
            )
        except Exception as exc:
            logger.error(
                "meeting_processing_failed",
                event_id=event.event_id,
                error=str(exc),
            )

        return []
