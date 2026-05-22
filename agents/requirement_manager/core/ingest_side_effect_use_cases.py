"""Application side effects for committed Requirement ingestion."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import FeishuMessengerPort
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .card_ports import RequirementCardRendererPort
from .meeting_ingest_workflow import IngestResult

logger = get_logger("requirement_manager.ingest_side_effects")


class RequirementIngestNotifierPort(Protocol):
    """Notification boundary for committed Requirement ingestion results."""

    async def send(
        self,
        *,
        channel: Any,
        title: str,
        content: str,
    ) -> Any:
        """Send one notification through an adapter-specific channel."""


class RequirementIngestEventPublisherPort(Protocol):
    """Outbox delivery boundary for already-staged Requirement ingest events."""

    async def publish_staged_event(
        self,
        event: Event,
        *,
        requirement_id: str | None,
    ) -> bool:
        """Publish one event that was staged in the local transaction."""


class RequirementIngestSideEffectUseCase:
    """Run post-commit external side effects for Requirement ingestion."""

    def __init__(
        self,
        *,
        event_publisher: RequirementIngestEventPublisherPort,
        notifier: RequirementIngestNotifierPort,
        notification_channel: Any,
    ) -> None:
        self._event_publisher = event_publisher
        self._notifier = notifier
        self._notification_channel = notification_channel

    async def publish_ingest_side_effects(self, result: IngestResult) -> None:
        """Publish integration events and notifications after ingest commit."""
        for event in result.staged_events:
            await self._event_publisher.publish_staged_event(
                event,
                requirement_id=None,
            )

        if result.requirements_extracted <= 0:
            return

        try:
            await self._notifier.send(
                channel=self._notification_channel,
                title="新需求待确认",
                content=(
                    f"从会议中提取了 {result.requirements_extracted} 个新需求，"
                    f"{result.questions_generated} 个待确认问题。"
                ),
            )
        except Exception as exc:
            logger.warning(
                "notification_send_failed",
                meeting_id=result.meeting_id,
                error=str(exc),
            )


class RequirementSessionExtractionCardUseCase:
    """Send committed session-extraction results through the messaging boundary."""

    def __init__(
        self,
        *,
        messenger: FeishuMessengerPort | None,
        card_renderer: RequirementCardRendererPort | None,
    ) -> None:
        self._messenger = messenger
        self._card_renderer = card_renderer

    async def send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ) -> None:
        """Send an extraction result card to the originating chat."""
        try:
            if self._messenger is None:
                logger.warning(
                    "session_extraction_card_skipped",
                    reason="messenger_port_not_configured",
                    chat_hash=hash_identifier(chat_id),
                    session_id=session_id,
                )
                return

            if self._card_renderer is None:
                logger.warning(
                    "session_extraction_card_skipped",
                    reason="card_renderer_not_configured",
                    chat_hash=hash_identifier(chat_id),
                    session_id=session_id,
                )
                return

            card = self._card_renderer.extraction_result_card(
                requirements=(
                    result.requirements if hasattr(result, "requirements") else []
                ),
                meeting_title=f"群聊会话 {session_id[:8]}...",
                questions_count=(
                    result.questions_generated
                    if hasattr(result, "questions_generated")
                    else 0
                ),
            )

            await self._messenger.send_card(
                receive_id=chat_id,
                receive_id_type="chat_id",
                card=card,
            )

            logger.info(
                "session_extraction_card_sent",
                chat_hash=hash_identifier(chat_id),
                session_id=session_id,
            )

        except Exception as exc:
            logger.error(
                "session_extraction_card_failed",
                chat_hash=hash_identifier(chat_id),
                session_id=session_id,
                error=str(exc),
            )
