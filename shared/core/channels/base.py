"""Channel messaging port."""

from abc import ABC, abstractmethod

from .types import ChannelCard, ChannelMessage, ChannelResponse


class MessageChannel(ABC):
    """Abstract port implemented by messaging platform adapters."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel identifier, such as ``feishu`` or ``wecom``."""
        ...

    @abstractmethod
    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """Send a text or Markdown message and return the platform message ID."""
        ...

    @abstractmethod
    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """Send a card message and return the platform message ID."""
        ...

    @abstractmethod
    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """Update a previously sent card."""
        ...

    @abstractmethod
    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """Handle a platform callback payload."""
        ...
