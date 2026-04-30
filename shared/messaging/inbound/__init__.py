"""Inbound messaging — unified message gateway for multi-platform routing."""

from .adapter import BasePlatformAdapter
from .gateway import UnifiedGateway
from .models import (
    ActionResponse,
    AgentResponse,
    CardAction,
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)
from .user_service import UserService

__all__ = [
    "Platform",
    "MessageType",
    "CardActionStyle",
    "UnifiedMessage",
    "CardAction",
    "UnifiedCard",
    "UnifiedAction",
    "AgentResponse",
    "ActionResponse",
    "BasePlatformAdapter",
    "UnifiedGateway",
    "UserService",
]
