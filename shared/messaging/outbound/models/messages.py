"""Channel message models."""
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from ulid import ULID

from shared.messaging.outbound.core.enums import ChatType, MediaType, ParseMode


def _generate_media_id() -> str:
    return f"med_{ULID()}"


def _generate_message_id() -> str:
    return f"msg_{ULID()}"


class MediaAttachment(BaseModel):
    """Media attachment in a message."""

    media_id: str = Field(default_factory=_generate_media_id)
    media_type: MediaType
    url: str | None = None
    local_path: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    duration: int | None = None
    thumbnail_url: str | None = None


class MessageAuthor(BaseModel):
    """Author of a message."""

    platform_user_id: str
    display_name: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    is_bot: bool = False


class ChatContext(BaseModel):
    """Chat/conversation context."""

    platform_chat_id: str
    chat_type: ChatType
    chat_name: str | None = None


class InboundMessage(BaseModel):
    """Message received from a platform."""

    message_id: str = Field(default_factory=_generate_message_id)
    channel_id: str
    platform_message_id: str
    author: MessageAuthor
    chat: ChatContext
    content: str | None = None
    attachments: list[MediaAttachment] = Field(default_factory=list)
    reply_to_message_id: str | None = None
    mentioned_user_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_payload: dict[str, Any] | None = Field(default=None, exclude=True)


class OutboundMessage(BaseModel):
    """Message to send to a platform."""

    message_id: str = Field(default_factory=_generate_message_id)
    channel_id: str
    target_chat_id: str
    content: str | None = None
    attachments: list[MediaAttachment] = Field(default_factory=list)
    reply_to_platform_message_id: str | None = None
    parse_mode: ParseMode = ParseMode.PLAIN
    silent: bool = False
    trace_id: str | None = None          # 端到端链路追踪 ID


class DeliveryResult(BaseModel):
    """Result of message delivery attempt."""

    success: bool
    platform_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    delivered_at: datetime | None = None
