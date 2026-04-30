# shared/services/feishu/adapter.py
"""
FeishuChannelAdapter - 飞书渠道适配器

将飞书客户端适配为 MessageChannel 接口。
"""
from typing import TYPE_CHECKING

from shared.integrations.channels import (
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
    飞书渠道适配器

    将 FeishuClient 适配为 MessageChannel 接口。
    """

    def __init__(self, client: "FeishuClient"):
        """
        Args:
            client: FeishuClient 实例
        """
        self._client = client

    @property
    def channel_name(self) -> str:
        """渠道标识"""
        return "feishu"

    async def send_message(self, user_id: str, content: ChannelMessage) -> str:
        """
        发送消息

        飞书使用 send_card 或 reply_message，这里简化为 send_card。
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
        发送卡片

        将通用 ChannelCard 转换为飞书卡片格式。
        """
        feishu_card = self._convert_to_feishu_card(card)
        return await self._client.send_card(
            receive_id=user_id,
            receive_id_type="open_id",
            card=feishu_card
        )

    async def update_card(self, message_id: str, card: ChannelCard) -> bool:
        """更新卡片"""
        feishu_card = self._convert_to_feishu_card(card)
        return await self._client.update_card(message_id, feishu_card)

    async def handle_callback(self, payload: dict) -> ChannelResponse:
        """
        处理回调

        注意：实际回调处理在 CardHandler 中，这里仅返回成功。
        """
        return ChannelResponse(success=True)

    def _convert_to_feishu_card(self, card: ChannelCard) -> dict:
        """将通用卡片转换为飞书格式"""
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
