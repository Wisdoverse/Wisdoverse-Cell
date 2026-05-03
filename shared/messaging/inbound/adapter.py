"""
BasePlatformAdapter - platform adapter abstract base class.

All platform adapters must implement this interface to provide unified message
handling.
"""

from abc import ABC, abstractmethod
from typing import Optional

from .models import Platform, UnifiedAction, UnifiedCard, UnifiedMessage


class BasePlatformAdapter(ABC):
    """
    Platform adapter base class.

    Responsibilities:
    1. Convert raw platform messages to UnifiedMessage.
    2. Convert UnifiedCard to the platform-native card format.
    3. Convert platform callbacks to UnifiedAction.
    4. Send messages to the platform.
    5. Fetch user information for identity mapping.
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """Return the platform handled by this adapter."""
        pass

    @abstractmethod
    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        Convert a raw platform message event to the unified format.

        Args:
            raw_event: Raw platform event data.

        Returns:
            UnifiedMessage, or None when the event cannot be parsed.
        """
        pass

    @abstractmethod
    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        Convert a platform card callback to a unified action.

        Args:
            raw_callback: Platform callback data.

        Returns:
            UnifiedAction, or None when the callback cannot be parsed.
        """
        pass

    @abstractmethod
    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        Send a card message.

        Args:
            chat_id: Conversation ID.
            card: Unified card model.

        Returns:
            Platform message ID.
        """
        pass

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> str:
        """
        Send a text message.

        Args:
            chat_id: Conversation ID.
            text: Message text.

        Returns:
            Platform message ID.
        """
        pass

    @abstractmethod
    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        Update a sent card.

        Args:
            message_id: Message ID to update.
            card: Replacement card content.

        Returns:
            Whether the update succeeded.
        """
        pass

    @abstractmethod
    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        Get a user email for cross-platform identity mapping.

        Args:
            platform_user_id: Platform user ID.

        Returns:
            User email or None.
        """
        pass

    @abstractmethod
    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        Get a user display name.

        Args:
            platform_user_id: Platform user ID.

        Returns:
            User name or None.
        """
        pass

    def build_platform_card(self, card: UnifiedCard) -> dict:
        """Convert UnifiedCard to platform-native card format.

        Default raises NotImplementedError. Subclasses that support
        cards should override. Replaces hasattr anti-pattern.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement build_platform_card"
        )
