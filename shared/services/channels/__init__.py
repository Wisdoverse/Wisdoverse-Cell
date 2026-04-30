"""Deprecated: use shared.integrations.channels"""
from shared.integrations.channels import (
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
