"""
OpenClawChannelAdapter - OpenClaw channel adapter.

Adapts OpenClawClient to the MessageChannel interface so agents can send
OpenClaw messages through ChannelRegistry.
"""
from typing import TYPE_CHECKING

from shared.core.channels import (
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    MessageChannel,
)
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from .client import OpenClawClient

logger = get_logger("openclaw.adapter")


class OpenClawChannelAdapter(MessageChannel):
    """
    OpenClaw channel adapter.

    Adapts OpenClawClient to MessageChannel for
    ChannelRegistry.get("openclaw").
    """

    def __init__(self, client: "OpenClawClient"):
        self._client = client

    @property
    def channel_name(self) -> str:
        return "openclaw"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """Send a text or Markdown message."""
        result = await self._client.send_request(
            "channel.sendText",
            params={
                "chat_id": user_id,
                "text": content.content,
                "format": content.message_type,
            },
        )
        return result.get("message_id", "")

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """Send a card message."""
        openclaw_card = self._convert_card(card)
        result = await self._client.send_request(
            "channel.sendCard",
            params={
                "chat_id": user_id,
                "card": openclaw_card,
            },
        )
        return result.get("message_id", "")

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """Update a sent card."""
        openclaw_card = self._convert_card(card)
        result = await self._client.send_request(
            "channel.updateCard",
            params={
                "message_id": message_id,
                "card": openclaw_card,
            },
        )
        return result.get("success", False)

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """Handle a card callback."""
        return ChannelResponse(success=True)

    def _convert_card(self, card: ChannelCard) -> dict:
        """Convert ChannelCard to the OpenClaw card format."""
        openclaw_card: dict = {
            "card_id": card.card_id,
            "title": card.title,
        }

        elements = []
        for element in card.elements:
            if element.element_type == "text":
                elements.append({"type": "text", "content": element.content or ""})
            elif element.element_type == "field" and element.fields:
                elements.append({"type": "fields", "fields": element.fields})
            elif element.element_type == "divider":
                elements.append({"type": "divider"})
        if elements:
            openclaw_card["elements"] = elements

        if card.actions:
            openclaw_card["actions"] = [
                {
                    "action_id": action.action_id,
                    "label": action.label,
                    "style": action.style,
                    "value": action.payload,
                }
                for action in card.actions
            ]

        return openclaw_card
