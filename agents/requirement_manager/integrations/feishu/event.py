"""
Feishu event subscription handler.

Supported events:
- vc.meeting.meeting_ended_v1: meeting ended
- calendar.calendar.event_changed_v4: calendar event changed
"""
from typing import Callable

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .acl import FeishuMeetingEndedEvent, FeishuRequirementCalendarEvent
from .cards.requirement import (
    build_calendar_reminder_card,
    build_requirement_extracted_card,
)

logger = get_logger("feishu.handlers.event")


class EventHandler:
    """
    Event subscription handler.

    Handles events pushed by Feishu.
    """

    def __init__(self, feishu_client, agent):
        self.client = feishu_client
        self.agent = agent

        self._handlers: dict[str, Callable] = {
            "vc.meeting.meeting_ended_v1": self._handle_meeting_ended,
            "calendar.calendar.event_changed_v4": self._handle_calendar_changed,
        }

    async def dispatch(self, event_type: str, data: dict) -> dict:
        """
        Dispatch events to the corresponding handler.

        Args:
            event_type: Event type.
            data: Complete event payload.

        Returns:
            Response payload.
        """
        handler = self._handlers.get(event_type)

        if not handler:
            logger.warning("unhandled_feishu_event", event_type=event_type)
            return {"code": 0}

        try:
            return await handler(data)
        except Exception as e:
            logger.error(
                "feishu_event_handler_error",
                event_type=event_type,
                error=str(e)
            )
            return {"code": 0}  # Return success to avoid retry

    async def _handle_meeting_ended(self, data: dict) -> dict:
        """
        Handle meeting-ended events.

        Flow:
        1. Extract meeting information.
        2. Call the agent to extract requirements.
        3. Send a notification card to the meeting chat.
        """
        meeting = FeishuMeetingEndedEvent.from_payload(data)

        logger.info(
            "meeting_ended_event",
            meeting_id=meeting.meeting_id,
            topic=meeting.topic,
            has_summary=meeting.has_summary,
        )

        if not meeting.has_summary:
            logger.info("meeting_no_summary", meeting_id=meeting.meeting_id)
            return {"code": 0}

        result = await self.agent.ingest_meeting(**meeting.ingest_kwargs())

        logger.info(
            "meeting_extraction_complete",
            meeting_id=meeting.meeting_id,
            requirements=result.requirements_extracted,
            questions=result.questions_generated,
        )

        if result.requirements_extracted > 0 and meeting.has_chat:
            try:
                card = build_requirement_extracted_card(
                    requirements=result.requirements if hasattr(result, 'requirements') else [],
                    meeting_title=meeting.topic,
                    questions_count=result.questions_generated,
                )
                await self.client.send_card(
                    receive_id=meeting.chat_id,
                    receive_id_type="chat_id",
                    card=card,
                )
                logger.info("meeting_card_sent", chat_hash=hash_identifier(meeting.chat_id))
            except Exception as e:
                logger.error("meeting_card_send_error", error=str(e))

        return {"code": 0}

    async def _handle_calendar_changed(self, data: dict) -> dict:
        """
        Handle calendar-changed events.

        Flow:
        1. Filter event types and only handle create/update.
        2. Check whether the title contains requirement-related keywords.
        3. If matched, send a reminder card to the organizer.
        """
        calendar_event = FeishuRequirementCalendarEvent.from_payload(data)

        logger.info(
            "calendar_event_received",
            event_id=calendar_event.event_id,
            summary_length=len(calendar_event.summary),
            change_type=calendar_event.change_type,
            has_organizer=calendar_event.has_organizer,
        )

        if not calendar_event.is_created_or_updated:
            logger.debug("calendar_event_skipped_type", change_type=calendar_event.change_type)
            return {"code": 0}

        if not calendar_event.has_requirement_keywords:
            logger.debug(
                "calendar_event_no_keyword_match",
                event_id=calendar_event.event_id,
                summary_length=len(calendar_event.summary),
            )
            return {"code": 0}

        logger.info(
            "calendar_event_keyword_matched",
            event_id=calendar_event.event_id,
            summary_hash=hash_identifier(calendar_event.summary),
            keywords=calendar_event.matched_keywords,
        )

        if calendar_event.has_organizer:
            try:
                card = build_calendar_reminder_card(**calendar_event.reminder_card_kwargs())
                await self.client.send_card(
                    receive_id=calendar_event.organizer_id,
                    receive_id_type="user_id",
                    card=card,
                )
                logger.info(
                    "calendar_reminder_sent",
                    event_id=calendar_event.event_id,
                    organizer_hash=hash_identifier(calendar_event.organizer_id),
                )
            except Exception as e:
                logger.error(
                    "calendar_reminder_send_error",
                    event_id=calendar_event.event_id,
                    error=str(e),
                )

        return {"code": 0}
