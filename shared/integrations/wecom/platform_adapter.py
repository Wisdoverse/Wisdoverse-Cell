# shared/services/wecom/platform_adapter.py
"""
WecomPlatformAdapter - 企业微信平台适配器

实现 BasePlatformAdapter 接口，用于统一网关的企微接入。
"""
import json
import xml.etree.ElementTree as ET
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

from .cards.builder import WecomCardBuilder

if TYPE_CHECKING:
    from .client import WecomClient

logger = get_logger("wecom.platform_adapter")


class WecomPlatformAdapter(BasePlatformAdapter):
    """
    企业微信平台适配器

    将企微消息/回调转换为统一格式，并将统一格式转换为企微格式发送。
    """

    def __init__(self, client: "WecomClient"):
        self._client = client
        self._user_cache: dict[str, dict] = {}

    @property
    def platform(self) -> Platform:
        return Platform.WECOM

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        将企微消息事件转换为统一格式

        企微消息原始格式为 XML，解析后传入此方法。

        Args:
            raw_event: 解析后的消息数据（从 XML 转换的 dict）

        Returns:
            UnifiedMessage 或 None
        """
        # 企微消息可能以 XML Element 或 dict 形式传入
        if isinstance(raw_event, ET.Element):
            raw_event = self._xml_to_dict(raw_event)

        msg_type = raw_event.get("MsgType", "text")
        user_id = raw_event.get("FromUserName", "")
        msg_id = raw_event.get("MsgId", "")

        if not user_id:
            return None

        # 消息内容
        content, unified_type, attachments = self._parse_content(msg_type, raw_event)

        # 时间戳
        create_time = raw_event.get("CreateTime", "")
        timestamp = self._parse_timestamp(create_time)

        return UnifiedMessage(
            platform=Platform.WECOM,
            message_id=msg_id or f"wecom_{int(timestamp.timestamp())}",
            chat_id=user_id,  # 企微私聊时 chat_id 即为 user_id
            chat_type="private",  # 企微应用消息默认私聊
            sender_id=user_id,
            sender_name="",  # 由 Gateway 通过 UserService 填充
            message_type=unified_type,
            content=content,
            mentions=[],
            attachments=attachments,
            timestamp=timestamp,
            raw_data=raw_event,
        )

    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        将企微卡片回调转换为统一格式

        Args:
            raw_callback: 企微卡片回调数据

        Returns:
            UnifiedAction 或 None
        """
        # 企微卡片回调格式
        # {
        #   "FromUserName": "user_id",
        #   "EventKey": "button_key",
        #   "ResponseCode": "xxx",
        #   "TaskId": "xxx"
        # }
        event_key = raw_callback.get("EventKey", "")
        if not event_key:
            return None

        operator_id = raw_callback.get("FromUserName", "")
        response_code = raw_callback.get("ResponseCode", "")

        # 解析 EventKey
        # 格式可能是: "action_id" 或 "action_id:payload_json"
        action_id, value = self._parse_event_key(event_key)

        return UnifiedAction(
            platform=Platform.WECOM,
            action_id=action_id,
            message_id=response_code,  # 用于更新卡片
            operator_id=operator_id,
            value=value,
            raw_data=raw_callback,
        )

    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        发送卡片消息

        Args:
            chat_id: 用户 ID
            card: 统一卡片格式

        Returns:
            消息 ID
        """
        wecom_card = self._build_wecom_card(card)
        return await self._client.send_template_card(chat_id, wecom_card)

    async def send_text(self, chat_id: str, text: str) -> str:
        """
        发送文本消息

        Args:
            chat_id: 用户 ID
            text: 文本内容

        Returns:
            消息 ID
        """
        return await self._client.send_text_message(chat_id, text)

    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        更新已发送的卡片

        Args:
            message_id: response_code（企微更新卡片用）
            card: 新的卡片内容

        Returns:
            是否成功
        """
        wecom_card = self._build_wecom_card(card)
        return await self._client.update_template_card(message_id, wecom_card)

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户邮箱

        Args:
            platform_user_id: 企微 UserID

        Returns:
            邮箱或 None
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("email") or None

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        获取用户名称

        Args:
            platform_user_id: 企微 UserID

        Returns:
            用户名或 None
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("name")

    # === Private Methods ===

    async def _get_user_info(self, user_id: str) -> dict:
        """获取用户信息（带缓存）"""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        user_info = await self._client.get_user_info(user_id)
        self._user_cache[user_id] = user_info
        return user_info

    def _xml_to_dict(self, root: ET.Element) -> dict:
        """将 XML Element 转换为 dict"""
        result = {}
        for child in root:
            result[child.tag] = child.text or ""
        return result

    def _parse_content(
        self, msg_type: str, raw_event: dict
    ) -> tuple[str, MessageType, list[dict]]:
        """
        解析消息内容

        Returns:
            (content, message_type, attachments)
        """
        attachments: list[dict] = []

        if msg_type == "text":
            content = raw_event.get("Content", "")
            return content, MessageType.TEXT, attachments

        elif msg_type == "image":
            media_id = raw_event.get("MediaId", "")
            pic_url = raw_event.get("PicUrl", "")
            attachments.append({
                "type": "image",
                "media_id": media_id,
                "url": pic_url,
            })
            return "[图片]", MessageType.IMAGE, attachments

        elif msg_type == "voice":
            media_id = raw_event.get("MediaId", "")
            attachments.append({
                "type": "voice",
                "media_id": media_id,
            })
            return "[语音]", MessageType.TEXT, attachments

        elif msg_type == "video":
            media_id = raw_event.get("MediaId", "")
            attachments.append({
                "type": "video",
                "media_id": media_id,
            })
            return "[视频]", MessageType.TEXT, attachments

        elif msg_type == "file":
            media_id = raw_event.get("MediaId", "")
            attachments.append({
                "type": "file",
                "media_id": media_id,
            })
            return "[文件]", MessageType.FILE, attachments

        else:
            return f"[{msg_type}]", MessageType.TEXT, attachments

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析企微时间戳（秒）"""
        if not timestamp_str:
            return datetime.now(UTC)

        try:
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (ValueError, TypeError):
            return datetime.now(UTC)

    def _parse_event_key(self, event_key: str) -> tuple[str, dict]:
        """
        解析 EventKey

        格式可能是:
        - "action_id"
        - "action_id:payload_json"

        Returns:
            (action_id, value_dict)
        """
        if ":" not in event_key:
            return event_key, {}

        parts = event_key.split(":", 1)
        action_id = parts[0]

        try:
            value = json.loads(parts[1])
            if not isinstance(value, dict):
                value = {"value": value}
        except (json.JSONDecodeError, IndexError):
            value = {}

        return action_id, value

    def _build_wecom_card(self, card: UnifiedCard) -> dict:
        """
        将 UnifiedCard 转换为企微模板卡片格式

        Args:
            card: 统一卡片格式

        Returns:
            企微模板卡片 dict
        """
        builder = WecomCardBuilder()

        # 标题
        title = card.title
        if card.status:
            title = f"[{card.status}] {title}"
        builder.set_title(title)

        # 描述（截取 Markdown 内容前 128 字符）
        description = card.content[:128] if card.content else ""
        if len(card.content) > 128:
            description += "..."
        builder.set_description(description)

        # 字段
        for field in card.fields[:6]:  # 企微最多 6 个字段
            builder.add_horizontal_content(
                key=field.get("label", ""),
                value=field.get("value", ""),
            )

        # 按钮（企微最多 2 个）
        for action in card.actions[:2]:
            style = self._map_action_style(action.style)

            # 构建 key，包含 action_id 和 value
            key = action.action_id
            if action.value or card.context:
                payload = {**action.value, **card.context}
                key = f"{action.action_id}:{json.dumps(payload, ensure_ascii=False)}"

            builder.add_button(
                text=action.label,
                key=key,
                style=style,
            )

        return builder.build()

    def _map_action_style(self, style: CardActionStyle) -> int:
        """
        将 CardActionStyle 映射为企微按钮样式

        企微样式: 1=蓝色, 2=灰色, 3=红色
        """
        style_map = {
            CardActionStyle.PRIMARY: 1,
            CardActionStyle.DEFAULT: 2,
            CardActionStyle.DANGER: 3,
        }
        return style_map.get(style, 2)
