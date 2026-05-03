"""Channel gateway event definitions."""
from typing import Literal

from pydantic import BaseModel

from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    OutboundMessage,
)


class ChannelEventTypes:
    """Event type constants for channel gateway."""

    MESSAGE_INBOUND = "channel.message.inbound"
    MESSAGE_OUTBOUND = "channel.message.outbound"
    MESSAGE_DELIVERED = "channel.message.delivered"
    MESSAGE_EDITED = "channel.message.edited"
    MESSAGE_DELETED = "channel.message.deleted"
    REACTION_ADDED = "channel.reaction.added"
    REACTION_REMOVED = "channel.reaction.removed"
    READ_RECEIPT = "channel.read.receipt"
    TYPING_STARTED = "channel.typing.started"
    ADAPTER_STATUS = "channel.adapter.status"


class MessageInboundPayload(BaseModel):
    """Payload for channel.message.inbound event."""

    message: InboundMessage


class MessageOutboundPayload(BaseModel):
    """Payload for channel.message.outbound event."""

    message: OutboundMessage


class MessageDeliveredPayload(BaseModel):
    """Payload for channel.message.delivered event."""

    message_id: str
    channel_id: str
    result: DeliveryResult


class MessageEditedPayload(BaseModel):
    """Payload for channel.message.edited event."""

    channel_id: str
    platform_message_id: str
    new_content: str


class MessageDeletedPayload(BaseModel):
    """Payload for channel.message.deleted event."""

    channel_id: str
    platform_message_id: str


class ReactionPayload(BaseModel):
    """Payload for channel.reaction.added/removed events."""

    channel_id: str
    platform_message_id: str
    user_id: str
    emoji: str


class ReadReceiptPayload(BaseModel):
    """Payload for channel.read.receipt event."""

    channel_id: str
    platform_message_id: str
    user_id: str


class TypingStartedPayload(BaseModel):
    """Payload for channel.typing.started event."""

    channel_id: str
    platform_chat_id: str
    user_id: str | None = None


class AdapterStatusPayload(BaseModel):
    """Payload for channel.adapter.status event."""

    channel_id: str
    status: Literal["connected", "disconnected", "error", "reconnecting"]
    error_message: str | None = None
