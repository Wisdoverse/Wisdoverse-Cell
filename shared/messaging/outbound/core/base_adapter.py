"""Base channel adapter interface."""
from abc import ABC, abstractmethod
from typing import AsyncIterator

from shared.messaging.outbound.core.enums import ChannelCapability, ChannelStatus
from shared.messaging.outbound.core.exceptions import NotSupportedError
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    OutboundMessage,
)


class BaseChannelAdapter(ABC):
    """Abstract base class for all channel adapters."""

    channel_id: str
    channel_name: str
    status: ChannelStatus
    capabilities: set[ChannelCapability]

    def has_capability(self, capability: ChannelCapability) -> bool:
        """Check if adapter supports a capability."""
        return capability in self.capabilities

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the platform."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the platform and cleanup resources."""
        pass

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send a message to the platform."""
        pass

    @abstractmethod
    async def listen(self) -> AsyncIterator[InboundMessage]:
        """Listen for incoming messages from the platform."""
        pass

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Edit an existing message. Override if supported."""
        raise NotSupportedError(self.channel_id, "edit_message")

    async def delete_message(self, message_id: str) -> bool:
        """Delete a message. Override if supported."""
        raise NotSupportedError(self.channel_id, "delete_message")

    async def add_reaction(self, message_id: str, emoji: str) -> bool:
        """Add reaction to a message. Override if supported."""
        raise NotSupportedError(self.channel_id, "add_reaction")

    async def remove_reaction(self, message_id: str, emoji: str) -> bool:
        """Remove reaction from a message. Override if supported."""
        raise NotSupportedError(self.channel_id, "remove_reaction")

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator. Override if supported."""
        raise NotSupportedError(self.channel_id, "send_typing_indicator")

    async def mark_as_read(self, message_id: str) -> None:
        """Mark message as read. Override if supported."""
        raise NotSupportedError(self.channel_id, "mark_as_read")
