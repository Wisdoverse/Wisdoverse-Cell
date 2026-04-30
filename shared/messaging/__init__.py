"""Messaging system — unified inbound orchestration + outbound delivery.

Preferred import path for all messaging components.
Example: from shared.messaging import UnifiedGateway, UnifiedMessage
"""
from shared.messaging.inbound.adapter import BasePlatformAdapter
from shared.messaging.inbound.gateway import UnifiedGateway
from shared.messaging.inbound.models import (
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
from shared.messaging.inbound.user_service import UserService

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
