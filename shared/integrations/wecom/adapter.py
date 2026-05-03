# shared/integrations/wecom/adapter.py
"""WecomChannelAdapter - 企微渠道适配器"""
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
    """企微渠道适配器 - 将 WecomClient 适配为 MessageChannel 接口"""

    def __init__(self, client: "WecomClient"):
        self._client = client

    @property
    def channel_name(self) -> str:
        """渠道标识"""
        return "wecom"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """发送文本消息"""
        return await self._client.send_text_message(user_id, content.content)

    async def send_card(self, user_id: str, card: ChannelCard) -> str:
        """发送卡片消息"""
        wecom_card = WecomCardBuilder.from_channel_card(card)
        return await self._client.send_template_card(user_id, wecom_card)

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """更新卡片"""
        wecom_card = WecomCardBuilder.from_channel_card(card)
        return await self._client.update_template_card(message_id, wecom_card)

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """处理回调"""
        return ChannelResponse(success=True)
