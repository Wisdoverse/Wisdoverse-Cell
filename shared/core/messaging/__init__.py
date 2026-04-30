"""Messaging Port interfaces — platform adapter ABC and core models."""
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
from .platform_adapter import BasePlatformAdapter

__all__ = [
    "BasePlatformAdapter",
    "ActionResponse", "AgentResponse", "CardAction", "CardActionStyle",
    "MessageType", "Platform", "UnifiedAction", "UnifiedCard", "UnifiedMessage",
]
