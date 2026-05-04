# shared/integrations/wecom/adapter.py
"""WecomChannelAdapter - WeCom channel adapter."""
from typing import TYPE_CHECKING

from shared.core.channels import (
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    MessageChannel,
)
from shared.utils.logger import get_logger

from .cards.builder import WecomCardBuilder

if TYPE_CHECKING:
    from .client import WecomClient

logger = get_logger("wecom.adapter")


class WecomChannelAdapter(MessageChannel):
    """WeCom channel adapter that adapts WecomClient to MessageChannel."""

    def __init__(self, client: "WecomClient"):
        self._client = client

    @property
    def channel_name(self) -> str:
        """Channel identifier."""
        return "wecom"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """Send a text message."""
        return await self._client.send_text_message(user_id, content.content)

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """Send a card message."""
        wecom_card = WecomCardBuilder.from_channel_card(card)
        return await self._client.send_template_card(user_id, wecom_card)

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """Update a card."""
        wecom_card = WecomCardBuilder.from_channel_card(card)
        return await self._client.update_template_card(message_id, wecom_card)

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """Handle a callback."""
        return ChannelResponse(success=True)
