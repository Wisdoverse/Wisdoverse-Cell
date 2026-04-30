# shared/integrations/channels/__init__.py
"""
Channels - 消息渠道抽象层

提供统一的消息渠道接口，支持多渠道（飞书、企微等）。
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
