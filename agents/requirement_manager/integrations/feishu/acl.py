"""Agent-local anti-corruption helpers for inbound Feishu events."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

REQUIREMENT_CALENDAR_KEYWORDS = (
    "需求",
    "产品",
    "review",
    "PRD",
    "评审",
    "规划",
    "迭代",
)
REQUIREMENT_CALENDAR_CHANGE_TYPES = frozenset({"created", "updated"})
UNKNOWN_TIME_LABEL = "未知时间"
BOT_COMMAND_PATTERN = re.compile(r"^/(\w+)(?:\s+(.*))?$")
DEFAULT_REQUIREMENT_REJECTION_REASON = "未提供原因"
DEFAULT_BATCH_REJECTION_REASON = "批量拒绝"


@dataclass(frozen=True, slots=True)
class FeishuBotCommand:
    """Domain-friendly command parsed from a Feishu bot text message."""

    name: str
    args: str | None = None


@dataclass(frozen=True, slots=True)
class FeishuBotMessage:
    """Domain-friendly view of a Feishu bot message event."""

    message_id: str
    chat_id: str
    message_type: str
    text: str
    command: FeishuBotCommand | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "FeishuBotMessage":
        """Translate a Feishu message payload into local bot-message fields."""
        message = _mapping(payload.get("message"))
        text = _message_text(message.get("content"))
        return cls(
            message_id=_text(message.get("message_id")),
            chat_id=_text(message.get("chat_id")),
            message_type=_text(message.get("message_type")),
            text=text,
            command=_bot_command(text),
        )

    @property
    def is_text(self) -> bool:
        """Return whether this Feishu event contains a text message."""
        return self.message_type == "text"

    @property
    def has_text(self) -> bool:
        """Return whether the text body has content for command or ingest handling."""
        return bool(self.text)

    @property
    def is_command(self) -> bool:
        """Return whether the text body is a bot command."""
        return self.command is not None

    def ingest_kwargs(self) -> dict[str, str]:
        """Return Requirement-ingest fields translated from Feishu bot vocabulary."""
        return {
            "content": self.text,
            "source": "feishu_bot",
        }


@dataclass(frozen=True, slots=True)
class FeishuCardAction:
    """Domain-friendly view of a Feishu interactive-card callback."""

    action_type: str
    operator_id: str
    requirement_id: str
    page: int
    chat_id: str
    requirement_ids: tuple[str, ...]
    reason: str
    reject_reason: str
    work_package_id: Any

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "FeishuCardAction":
        """Translate a Feishu card callback payload into local action fields."""
        action = _mapping(payload.get("action"))
        value = _mapping(action.get("value"))
        form_value = _mapping(action.get("form_value"))
        operator = _mapping(payload.get("operator"))
        return cls(
            action_type=_text(value.get("action")),
            operator_id=_text(operator.get("open_id")),
            requirement_id=_text(value.get("req_id")),
            page=_int(value.get("page"), default=1),
            chat_id=_text(value.get("chat_id")),
            requirement_ids=_text_sequence(value.get("req_ids")),
            reason=_text(form_value.get("reason")) or _text(value.get("reason")),
            reject_reason=_text(form_value.get("reject_reason"))
            or _text(value.get("reject_reason")),
            work_package_id=value.get("wp_id"),
        )

    @property
    def has_requirement_id(self) -> bool:
        """Return whether this callback names a Requirement entity."""
        return bool(self.requirement_id)

    @property
    def has_requirement_ids(self) -> bool:
        """Return whether this callback names multiple Requirement entities."""
        return bool(self.requirement_ids)

    @property
    def has_work_package_id(self) -> bool:
        """Return whether this callback names a PJM work package."""
        return bool(self.work_package_id)

    @property
    def requirement_rejection_reason(self) -> str:
        """Return the Requirement rejection reason with the legacy fallback."""
        return self.reason or DEFAULT_REQUIREMENT_REJECTION_REASON

    @property
    def batch_rejection_reason(self) -> str:
        """Return the batch rejection reason with the legacy fallback."""
        return self.reason or DEFAULT_BATCH_REJECTION_REASON

    @property
    def decomposition_rejection_reason(self) -> str:
        """Return the PJM decomposition rejection reason."""
        return self.reject_reason

    def requirement_ids_list(self) -> list[str]:
        """Return a mutable ID list for application-service boundaries."""
        return list(self.requirement_ids)


@dataclass(frozen=True, slots=True)
class FeishuCardActionResponse:
    """Published callback response shape for Feishu interactive-card actions."""

    toast_type: str | None = None
    toast_content: str | None = None
    card: Any | None = None

    @classmethod
    def info(cls, content: str) -> "FeishuCardActionResponse":
        """Return an informational toast response."""
        return cls(toast_type="info", toast_content=content)

    @classmethod
    def success(cls, content: str, *, card: Any | None = None) -> "FeishuCardActionResponse":
        """Return a success toast response, optionally with an updated card."""
        return cls(toast_type="success", toast_content=content, card=card)

    @classmethod
    def error(cls, content: str) -> "FeishuCardActionResponse":
        """Return an error toast response."""
        return cls(toast_type="error", toast_content=content)

    @classmethod
    def card_only(cls, card: Any) -> "FeishuCardActionResponse":
        """Return a response that replaces the card without showing a toast."""
        return cls(card=card)

    def to_payload(self) -> dict[str, Any]:
        """Return the Feishu callback payload expected by the shared router."""
        payload: dict[str, Any] = {}
        if self.toast_type and self.toast_content:
            payload["toast"] = {
                "type": self.toast_type,
                "content": self.toast_content,
            }
        if self.card is not None:
            payload["card"] = self.card
        return payload


@dataclass(frozen=True, slots=True)
class FeishuMeetingEndedEvent:
    """Domain-friendly view of a Feishu meeting-ended event."""

    meeting_id: str
    topic: str
    chat_id: str
    summary: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "FeishuMeetingEndedEvent":
        """Translate a Feishu meeting-ended payload into local event fields."""
        event = _mapping(payload.get("event"))
        meeting = _mapping(event.get("meeting"))
        return cls(
            meeting_id=_text(meeting.get("meeting_id")),
            topic=_text(meeting.get("topic")),
            chat_id=_text(meeting.get("chat_id")),
            summary=_text(meeting.get("summary")),
        )

    @property
    def has_summary(self) -> bool:
        """Return whether this event has extractable meeting content."""
        return bool(self.summary)

    @property
    def has_chat(self) -> bool:
        """Return whether a Feishu chat is available for notification."""
        return bool(self.chat_id)

    def ingest_kwargs(self) -> dict[str, str]:
        """Return Requirement-ingest fields translated from Feishu vocabulary."""
        return {
            "content": self.summary,
            "source": "feishu_meeting",
            "title": self.topic,
            "source_id": self.meeting_id,
        }


@dataclass(frozen=True, slots=True)
class FeishuRequirementCalendarEvent:
    """Domain-friendly view of a Feishu calendar event relevant to requirements."""

    event_id: str
    summary: str
    change_type: str
    organizer_id: str
    organizer_name: str
    start_time_label: str
    attendees: tuple[str, ...]
    matched_keywords: tuple[str, ...]

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        keywords: Sequence[str] = REQUIREMENT_CALENDAR_KEYWORDS,
    ) -> "FeishuRequirementCalendarEvent":
        """Translate a Feishu calendar payload into local reminder fields."""
        event = _mapping(payload.get("event"))
        calendar_event = _mapping(event.get("event"))
        organizer = _mapping(calendar_event.get("organizer"))
        return cls(
            event_id=_text(calendar_event.get("event_id")),
            summary=_text(calendar_event.get("summary")),
            change_type=_text(event.get("type")),
            organizer_id=_text(organizer.get("user_id")),
            organizer_name=_text(organizer.get("display_name")),
            start_time_label=_start_time_label(calendar_event.get("start_time")),
            attendees=_attendee_names(calendar_event.get("attendees")),
            matched_keywords=_matched_keywords(
                _text(calendar_event.get("summary")),
                keywords=keywords,
            ),
        )

    @property
    def is_created_or_updated(self) -> bool:
        """Return whether this Feishu change type should be considered."""
        return self.change_type in REQUIREMENT_CALENDAR_CHANGE_TYPES

    @property
    def has_requirement_keywords(self) -> bool:
        """Return whether the title matches Requirement-domain keywords."""
        return bool(self.matched_keywords)

    @property
    def has_organizer(self) -> bool:
        """Return whether an organizer can receive a reminder card."""
        return bool(self.organizer_id)

    @property
    def should_notify(self) -> bool:
        """Return whether this calendar event warrants a Requirement reminder."""
        return self.is_created_or_updated and self.has_requirement_keywords

    def reminder_card_kwargs(self) -> dict[str, Any]:
        """Return Feishu card-renderer fields from local reminder vocabulary."""
        return {
            "event_title": self.summary,
            "start_time": self.start_time_label,
            "organizer": self.organizer_name,
            "attendees": list(self.attendees),
            "keywords_found": list(self.matched_keywords),
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        return (str(value),)
    return tuple(str(item) for item in value)


def _matched_keywords(summary: str, *, keywords: Sequence[str]) -> tuple[str, ...]:
    if not summary:
        return ()
    pattern = re.compile("|".join(re.escape(keyword) for keyword in keywords), re.IGNORECASE)
    return tuple(dict.fromkeys(pattern.findall(summary)))


def _message_text(value: Any) -> str:
    content = _text(value)
    if not content:
        return ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(parsed, Mapping):
        return _text(parsed.get("text"))
    return _text(parsed)


def _bot_command(text: str) -> FeishuBotCommand | None:
    match = BOT_COMMAND_PATTERN.match(text.strip())
    if not match:
        return None
    command, args = match.groups()
    return FeishuBotCommand(name=command.lower(), args=args)


def _start_time_label(value: Any) -> str:
    start_time = _mapping(value)
    timestamp = _text(start_time.get("timestamp"))
    if timestamp:
        try:
            dt = datetime.fromtimestamp(int(timestamp))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return UNKNOWN_TIME_LABEL
    return _text(start_time.get("date")) or UNKNOWN_TIME_LABEL


def _attendee_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for attendee in value[:10]:
        attendee_mapping = _mapping(attendee)
        display_name = _text(attendee_mapping.get("display_name"))
        if display_name:
            names.append(display_name)
    return tuple(names)


__all__ = [
    "BOT_COMMAND_PATTERN",
    "DEFAULT_BATCH_REJECTION_REASON",
    "DEFAULT_REQUIREMENT_REJECTION_REASON",
    "FeishuBotCommand",
    "FeishuBotMessage",
    "FeishuCardAction",
    "FeishuCardActionResponse",
    "FeishuMeetingEndedEvent",
    "FeishuRequirementCalendarEvent",
    "REQUIREMENT_CALENDAR_CHANGE_TYPES",
    "REQUIREMENT_CALENDAR_KEYWORDS",
    "UNKNOWN_TIME_LABEL",
]
