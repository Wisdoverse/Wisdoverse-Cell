"""Application use cases for chat-session Requirement extraction."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from shared.utils.logger import get_logger

from .unit_of_work_ports import RequirementUnitOfWork, RequirementUnitOfWorkFactory

logger = get_logger("requirement_manager.session_extraction")


class RequirementSessionExtractionAgent(Protocol):
    """Runtime boundary used by session extraction orchestration."""

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
    ) -> Any:
        """Ingest formatted session content inside the existing transaction."""

    async def publish_ingest_side_effects(self, result: Any) -> None:
        """Publish post-commit ingestion side effects."""

    async def send_session_extraction_card(
        self,
        chat_id: str,
        result: Any,
        session_id: str,
    ) -> None:
        """Send a session extraction result card."""


class RequirementSessionExtractionUseCase:
    """Extract requirements from a recorded chat session."""

    def __init__(
        self,
        *,
        agent: RequirementSessionExtractionAgent,
        uow_factory: RequirementUnitOfWorkFactory,
    ) -> None:
        self._agent = agent
        self._uow_factory = uow_factory

    async def extract_from_session(self, session_id: str) -> Any | None:
        async with self._uow_factory() as uow:
            messages = await uow.messages.get_by_session(session_id)
            if not messages:
                logger.warning("extract_from_session_no_messages", session_id=session_id)
                return None

            chat_id = messages[0].chat_id
            content = format_messages_for_extraction(messages)

            logger.info(
                "extract_from_session_starting",
                session_id=session_id,
                message_count=len(messages),
                content_length=len(content),
            )

            result = await self._agent.ingest_meeting_with_uow(
                content=content,
                source="feishu_session",
                uow=uow,
                context=(
                    f"Session {session_id} from chat {chat_id} "
                    f"with {len(messages)} messages"
                ),
            )

            if result and result.requirements_extracted > 0:
                await uow.messages.mark_extracted(
                    session_id,
                    result.requirement_ids,
                )
                await self._link_requirements_to_messages(
                    requirement_ids=result.requirement_ids,
                    messages=messages,
                    uow=uow,
                )

            await uow.commit()

        await self._agent.publish_ingest_side_effects(result)

        if result and result.requirements_extracted > 0:
            await self._agent.send_session_extraction_card(
                chat_id,
                result,
                session_id,
            )
            logger.info(
                "extract_from_session_complete",
                session_id=session_id,
                requirements_extracted=result.requirements_extracted,
            )

        return result

    async def _link_requirements_to_messages(
        self,
        *,
        requirement_ids: list[str],
        messages: list[Any],
        uow: RequirementUnitOfWork,
    ) -> None:
        message_ids = [message.id for message in messages]
        for requirement_id in requirement_ids:
            requirement = await uow.requirements.get_by_id(requirement_id)
            if requirement and hasattr(requirement, "context_message_ids"):
                requirement.context_message_ids = message_ids


def format_messages_for_extraction(messages: list[Any]) -> str:
    """Format chat messages as conversation text for LLM extraction."""
    lines = []

    for message in messages:
        sender = message.sender_name or "Unknown"
        time_str = message.sent_at.strftime("%H:%M") if message.sent_at else "??:??"
        content = message.content or ""

        if not content.strip():
            continue

        lines.append(f"[{time_str}] {sender}: {content}")

    return "\n".join(lines)
