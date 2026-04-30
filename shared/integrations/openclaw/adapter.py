"""
OpenClawChannelAdapter - OpenClaw 渠道适配器

将 OpenClawClient 适配为 MessageChannel 接口，
使所有 Agent 可通过 ChannelRegistry 发送 OpenClaw 消息。
"""
from typing import TYPE_CHECKING

from shared.integrations.channels import (
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
    OpenClaw 渠道适配器

    将 OpenClawClient 适配为 MessageChannel 接口，
    供 Agent 通过 ChannelRegistry.get("openclaw") 使用。
    """

    def __init__(self, client: "OpenClawClient"):
        self._client = client

    @property
    def channel_name(self) -> str:
        return "openclaw"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """发送文本/Markdown 消息"""
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
        """发送卡片消息"""
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
        """更新已发送的卡片"""
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
        """处理回调"""
        return ChannelResponse(success=True)

    def _convert_card(self, card: ChannelCard) -> dict:
        """将 ChannelCard 转换为 OpenClaw 卡片格式"""
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
