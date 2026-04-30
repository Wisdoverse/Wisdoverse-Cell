# shared/integrations/feishu/platform_adapter.py
"""
FeishuPlatformAdapter - 飞书平台适配器

实现 BasePlatformAdapter 接口，用于统一网关的飞书接入。
"""
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from shared.messaging.inbound.adapter import BasePlatformAdapter
from shared.messaging.inbound.models import (
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)
from shared.utils.logger import get_logger

from .cards.builder import CardBuilder

if TYPE_CHECKING:
    from .client import FeishuClient

logger = get_logger("feishu.platform_adapter")


class FeishuPlatformAdapter(BasePlatformAdapter):
    """
    飞书平台适配器

    将飞书消息/回调转换为统一格式，并将统一格式转换为飞书格式发送。
    """

    def __init__(self, client: "FeishuClient"):
        self._client = client
        self._user_cache: dict[str, dict] = {}

    @property
    def platform(self) -> Platform:
        return Platform.FEISHU

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        将飞书消息事件转换为统一格式

        Args:
            raw_event: 飞书 im.message.receive_v1 事件数据

        Returns:
            UnifiedMessage 或 None
        """
        message = raw_event.get("message") or {}
        sender = raw_event.get("sender") or {}

        message_id = message.get("message_id", "")
        if not message_id:
            return None

        # 会话信息
        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "p2p")
        chat_type_mapped = "group" if chat_type == "group" else "private"

        # 发送者
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        sender_type = sender.get("sender_type", "")

        # 跳过机器人自己的消息
        if sender_type == "app":
            return None

        # 消息类型和内容
        msg_type = message.get("message_type", "text")
        content_str = message.get("content", "{}")
        content, unified_type, mentions, attachments = self._parse_content(
            msg_type, content_str
        )

        # 时间戳
        create_time = message.get("create_time", "")
        timestamp = self._parse_timestamp(create_time)

        return UnifiedMessage(
            platform=Platform.FEISHU,
            message_id=message_id,
            chat_id=chat_id,
            chat_type=chat_type_mapped,
            sender_id=sender_id,
            sender_name="",  # 由 Gateway 通过 UserService 填充
            message_type=unified_type,
            content=content,
            mentions=mentions,
            attachments=attachments,
            timestamp=timestamp,
            raw_data=raw_event,
        )

    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        将飞书卡片回调转换为统一格式

        Args:
            raw_callback: 飞书卡片回调数据

        Returns:
            UnifiedAction 或 None
        """
        action = raw_callback.get("action", {})
        action_value = action.get("value", {})
        action_id = action_value.get("action", "")

        if not action_id:
            return None

        # 操作者
        operator = raw_callback.get("operator", {})
        operator_id = operator.get("open_id", "")

        # 消息 ID
        open_message_id = raw_callback.get("open_message_id", "")

        return UnifiedAction(
            platform=Platform.FEISHU,
            action_id=action_id,
            message_id=open_message_id,
            operator_id=operator_id,
            value=action_value,
            raw_data=raw_callback,
        )

    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        发送卡片消息

        Args:
            chat_id: 会话 ID (chat_id 或 open_id)
            card: 统一卡片格式

        Returns:
            消息 ID
        """
        feishu_card = self._build_feishu_card(card)

        # 判断 ID 类型
        receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"

        return await self._client.send_card(
            receive_id=chat_id,
            receive_id_type=receive_id_type,
            card=feishu_card,
        )

    async def send_text(self, chat_id: str, text: str) -> str:
        """
        发送文本消息

        Args:
            chat_id: 会话 ID
            text: 文本内容

        Returns:
            消息 ID
        """
        # 使用卡片发送文本以保持格式一致
        builder = CardBuilder()
        builder.add_markdown(text)
        card = builder.build()

        receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"

        return await self._client.send_card(
            receive_id=chat_id,
            receive_id_type=receive_id_type,
            card=card,
        )

    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        更新已发送的卡片

        Args:
            message_id: 消息 ID
            card: 新的卡片内容

        Returns:
            是否成功
        """
        feishu_card = self._build_feishu_card(card)
        return await self._client.update_card(message_id, feishu_card)

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户邮箱

        Args:
            platform_user_id: 飞书 open_id

        Returns:
            邮箱或 None
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("email")

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户名称

        Args:
            platform_user_id: 飞书 open_id

        Returns:
            用户名或 None
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("name")

    # === Private Methods ===

    async def _get_user_info(self, open_id: str) -> dict:
        """获取用户信息（带缓存）"""
        if open_id in self._user_cache:
            return self._user_cache[open_id]

        user_info = await self._client.get_user_info(open_id)
        self._user_cache[open_id] = user_info
        return user_info

    def _parse_content(
        self, msg_type: str, content_str: str
    ) -> tuple[str, MessageType, list[str], list[dict]]:
        """
        解析消息内容

        Returns:
            (content, message_type, mentions, attachments)
        """
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            return content_str, MessageType.TEXT, [], []

        mentions: list[str] = []
        attachments: list[dict] = []

        if msg_type == "text":
            text = content.get("text", "")
            return text, MessageType.TEXT, mentions, attachments

        elif msg_type == "post":
            text = self._extract_post_text(content)
            return text, MessageType.POST, mentions, attachments

        elif msg_type == "image":
            image_key = content.get("image_key", "")
            attachments.append({
                "type": "image",
                "key": image_key,
                "url": "",  # 需要额外 API 获取
            })
            return f"[图片: {image_key}]", MessageType.IMAGE, mentions, attachments

        elif msg_type == "file":
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "")
            attachments.append({
                "type": "file",
                "key": file_key,
                "name": file_name,
            })
            return f"[文件: {file_name}]", MessageType.FILE, mentions, attachments

        else:
            return f"[{msg_type}]", MessageType.TEXT, mentions, attachments

    def _extract_post_text(self, content: dict) -> str:
        """从富文本中提取纯文本"""
        texts = []

        title = content.get("title", "")
        if title:
            texts.append(title)

        paragraphs = content.get("content", [])
        for paragraph in paragraphs:
            for element in paragraph:
                tag = element.get("tag", "")
                if tag == "text":
                    texts.append(element.get("text", ""))
                elif tag == "a":
                    texts.append(element.get("text", ""))
                elif tag == "at":
                    texts.append(f"@{element.get('user_name', '')}")

        return " ".join(texts)

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析飞书时间戳（毫秒）"""
        if not timestamp_str:
            return datetime.now(UTC)

        try:
            timestamp_ms = int(timestamp_str)
            return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        except (ValueError, TypeError):
            return datetime.now(UTC)

    def _build_feishu_card(self, card: UnifiedCard) -> dict:
        """
        将 UnifiedCard 转换为飞书卡片格式

        Args:
            card: 统一卡片格式

        Returns:
            飞书卡片 JSON
        """
        builder = CardBuilder()

        # Header
        header_template = self._get_header_template(card.status_color)
        if card.status:
            builder.set_header(card.title, template=header_template, subtitle=card.status)
        else:
            builder.set_header(card.title, template=header_template)

        # Content (Markdown)
        if card.content:
            builder.add_markdown(card.content)

        # Fields
        if card.fields:
            fields = [(f.get("label", ""), f.get("value", "")) for f in card.fields]
            builder.add_fields(fields)

        # Priority tag (if exists)
        if card.priority:
            builder.add_note(f"优先级: {card.priority}")

        # Actions
        if card.actions:
            builder.add_divider()
            buttons = []
            for action in card.actions:
                button_type = self._map_action_style(action.style)
                buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": action.label},
                    "type": button_type,
                    "value": {
                        "action": action.action_id,
                        **action.value,
                        **card.context,  # 透传上下文
                    },
                })
            builder.add_action_buttons(buttons)

        return builder.build()

    def _get_header_template(self, status_color: Optional[str]) -> str:
        """根据状态颜色获取卡片头部模板"""
        color_map = {
            "green": "green",
            "orange": "orange",
            "red": "red",
            "blue": "blue",
            "grey": "grey",
        }
        return color_map.get(status_color or "", "blue")

    def _map_action_style(self, style: CardActionStyle) -> str:
        """将 CardActionStyle 映射为飞书按钮类型"""
        style_map = {
            CardActionStyle.PRIMARY: "primary",
            CardActionStyle.DANGER: "danger",
            CardActionStyle.DEFAULT: "default",
        }
        return style_map.get(style, "default")
