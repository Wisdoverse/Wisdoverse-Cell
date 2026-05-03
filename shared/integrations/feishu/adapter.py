# shared/integrations/feishu/adapter.py
"""
FeishuChannelAdapter - Feishu channel adapter.

Adapts the Feishu client to the MessageChannel interface.
"""
from typing import TYPE_CHECKING

from shared.core.channels import (
    ChannelCard,
    ChannelMessage,
    ChannelResponse,
    MessageChannel,
)
from shared.utils.logger import get_logger

from .cards.builder import CardBuilder

if TYPE_CHECKING:
    from .client import FeishuClient

logger = get_logger("feishu.adapter")


class FeishuChannelAdapter(MessageChannel):
    """
    Feishu channel adapter.

    Adapts FeishuClient to MessageChannel.
    """

    def __init__(self, client: "FeishuClient"):
        """
        Args:
            client: FeishuClient instance.
        """
        self._client = client

    @property
    def channel_name(self) -> str:
        """Return the channel name."""
        return "feishu"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """
        Send a message.

        Feishu uses send_card or reply_message; this adapter routes through
        send_card for the generic channel boundary.
        """
        builder = CardBuilder()
        if content.message_type == "markdown":
            builder.add_markdown(content.content)
        else:
            builder.add_plain_text(content.content)

        card = builder.build()
        return await self._client.send_card(
            receive_id=user_id,
            receive_id_type="open_id",
            card=card
        )

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """
        Send a card.

        Converts a generic ChannelCard to Feishu card format.
        """
        feishu_card = self._convert_to_feishu_card(card)
        return await self._client.send_card(
            receive_id=user_id,
            receive_id_type="open_id",
            card=feishu_card
        )

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """Update a card."""
        feishu_card = self._convert_to_feishu_card(card)
        return await self._client.update_card(message_id, feishu_card)

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """
        Handle a callback.

        Actual callback handling lives in CardHandler; this boundary only
        acknowledges the callback.
        """
        return ChannelResponse(success=True)

    def _convert_to_feishu_card(self, card: ChannelCard) -> dict:
        """Convert a generic ChannelCard to Feishu format."""
        builder = CardBuilder()
        builder.set_header(card.title, template="blue")

        for element in card.elements:
            if element.element_type == "text":
                builder.add_plain_text(element.content or "")
            elif element.element_type == "field" and element.fields:
                fields = [(f.get("label", ""), f.get("value", "")) for f in element.fields]
                builder.add_fields(fields)
            elif element.element_type == "divider":
                builder.add_divider()

        if card.actions:
            buttons = []
            for action in card.actions:
                button_type = "default"
                if action.style == "primary":
                    button_type = "primary"
                elif action.style == "danger":
                    button_type = "danger"

                buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": action.label},
                    "type": button_type,
                    "value": {
                        "action": action.action_id,
                        **action.payload
                    }
                })
            builder.add_action_buttons(buttons)

        return builder.build()
