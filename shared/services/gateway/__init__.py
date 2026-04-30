"""Deprecated: use shared.messaging.inbound or shared.messaging"""
from shared.messaging.inbound import (
    ActionResponse,
    AgentResponse,
    BasePlatformAdapter,
    CardAction,
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedGateway,
    UnifiedMessage,
    UserService,
)

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
