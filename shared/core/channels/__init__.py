"""Channel messaging ports and value objects.

Concrete platform adapters live under ``shared.integrations``. Runtime code
should import these abstractions from ``shared.core.channels``.
"""

from .base import MessageChannel
from .registry import ChannelRegistry
from .types import (
    CardAction,
    CardElement,
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    IncomingMessage,
)

__all__ = [
    "MessageChannel",
    "ChannelRegistry",
    "ChannelMessage",
    "CardElement",
    "CardAction",
    "ChannelCard",
    "IncomingMessage",
    "ChannelResponse",
]
