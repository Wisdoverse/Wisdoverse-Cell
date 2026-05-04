"""Deprecated: use shared.core.channels."""

from shared.core.channels import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelRegistry,
    ChannelResponse,
    IncomingMessage,
    MessageChannel,
)

__all__ = [
    "MessageChannel", "ChannelRegistry", "ChannelMessage",
    "CardElement", "CardAction", "ChannelCard",
    "IncomingMessage", "ChannelResponse",
]
