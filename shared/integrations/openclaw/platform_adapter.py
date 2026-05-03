"""
OpenClawPlatformAdapter - OpenClaw 平台适配器

实现 BasePlatformAdapter 接口，用于统一网关的 OpenClaw 接入。
将 OpenClaw Gateway 事件转换为 UnifiedMessage，并通过 Gateway 发送响应。
"""
from datetime import UTC, datetime
from typing import Optional

from shared.messaging.inbound.adapter import BasePlatformAdapter
from shared.messaging.inbound.models import (
    CardActionStyle,
    MessageType,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)
from shared.models.platform import Platform
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .client import OpenClawClient

logger = get_logger("openclaw.platform_adapter")

# OpenClaw message type → UnifiedMessage MessageType
_MSG_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "file": MessageType.FILE,
    "rich_text": MessageType.POST,
    "card": MessageType.CARD,
}


class OpenClawPlatformAdapter(BasePlatformAdapter):
    """
    OpenClaw 平台适配器

    通过 OpenClawClient (WebSocket) 与 OpenClaw Gateway 通信，
    将 OpenClaw 事件转换为统一格式，并将统一格式转换为 OpenClaw RPC 调用发送。
    """

    def __init__(self, client: OpenClawClient):
        self._client = client
        self._user_cache: dict[str, dict] = {}

    @property
    def platform(self) -> Platform:
        return Platform.OPENCLAW

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        将 OpenClaw 入站消息事件转换为统一格式

        预期 raw_event 结构:
        {
            "message_id": "...",
            "channel": "whatsapp",  # 原始平台
            "chat_id": "...",
            "chat_type": "private" | "group",
            "sender": {
                "id": "...",
                "name": "...",
            },
            "content": "...",
            "message_type": "text" | "image" | "file" | "rich_text",
            "timestamp": 1706500000,
            "mentions": [],
            "attachments": [],
        }
        """
        message_id = raw_event.get("message_id", "")
        if not message_id:
            return None

        sender = raw_event.get("sender", {})
        sender_id = sender.get("id", "")
        if not sender_id:
            return None

        # 消息类型映射
        raw_type = raw_event.get("message_type", "text")
        message_type = _MSG_TYPE_MAP.get(raw_type, MessageType.TEXT)

        # 时间戳处理
        ts = raw_event.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts, tz=UTC)
        else:
            timestamp = datetime.now(UTC)

        return UnifiedMessage(
            platform=Platform.OPENCLAW,
            message_id=message_id,
            chat_id=raw_event.get("chat_id", ""),
            chat_type=raw_event.get("chat_type", "private"),
            sender_id=sender_id,
            sender_name=sender.get("name", ""),
            message_type=message_type,
            content=raw_event.get("content", ""),
            mentions=raw_event.get("mentions", []),
            attachments=raw_event.get("attachments", []),
            timestamp=timestamp,
            raw_data=raw_event,
        )

    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        将 OpenClaw 卡片回调转换为统一格式

        预期 raw_callback 结构:
        {
            "action_id": "approve",
            "message_id": "...",
            "operator": {
                "id": "...",
            },
            "value": {...},
        }
        """
        action_id = raw_callback.get("action_id", "")
        if not action_id:
            return None

        operator = raw_callback.get("operator", {})
        operator_id = operator.get("id", "")

        return UnifiedAction(
            platform=Platform.OPENCLAW,
            action_id=action_id,
            message_id=raw_callback.get("message_id", ""),
            operator_id=operator_id,
            value=raw_callback.get("value", {}),
            raw_data=raw_callback,
        )

    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        通过 OpenClaw Gateway 发送卡片消息

        Args:
            chat_id: 会话 ID
            card: 统一卡片格式

        Returns:
            消息 ID
        """
        openclaw_card = self._build_openclaw_card(card)

        result = await self._client.send_request(
            "channel.sendCard",
            params={
                "chat_id": chat_id,
                "card": openclaw_card,
            },
        )
        return result.get("message_id", "")

    async def send_text(self, chat_id: str, text: str) -> str:
        """
        通过 OpenClaw Gateway 发送文本消息

        Args:
            chat_id: 会话 ID
            text: 文本内容

        Returns:
            消息 ID
        """
        result = await self._client.send_request(
            "channel.sendText",
            params={
                "chat_id": chat_id,
                "text": text,
            },
        )
        return result.get("message_id", "")

    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        通过 OpenClaw Gateway 更新已发送的卡片

        Args:
            message_id: 消息 ID
            card: 新的卡片内容

        Returns:
            是否成功
        """
        openclaw_card = self._build_openclaw_card(card)

        result = await self._client.send_request(
            "channel.updateCard",
            params={
                "message_id": message_id,
                "card": openclaw_card,
            },
        )
        return result.get("success", False)

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        通过 OpenClaw Gateway 获取用户邮箱

        Args:
            platform_user_id: OpenClaw 用户 ID

        Returns:
            邮箱或 None
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("email")

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        通过 OpenClaw Gateway 获取用户名称

        Args:
            platform_user_id: OpenClaw 用户 ID

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

        try:
            result = await self._client.send_request(
                "user.getInfo",
                params={"user_id": user_id},
            )
            self._user_cache[user_id] = result
            return result
        except Exception:
            logger.warning("openclaw_user_info_failed", user_hash=hash_identifier(user_id))
            return {}

    def _build_openclaw_card(self, card: UnifiedCard) -> dict:
        """
        将 UnifiedCard 转换为 OpenClaw 卡片格式

        Args:
            card: 统一卡片

        Returns:
            OpenClaw 卡片 JSON
        """
        openclaw_card: dict = {
            "title": card.title,
            "content": card.content,
        }

        if card.status:
            openclaw_card["status"] = card.status
        if card.status_color:
            openclaw_card["status_color"] = card.status_color
        if card.priority:
            openclaw_card["priority"] = card.priority

        if card.fields:
            openclaw_card["fields"] = card.fields

        if card.actions:
            openclaw_card["actions"] = [
                {
                    "label": action.label,
                    "action_id": action.action_id,
                    "value": action.value,
                    "style": self._map_action_style(action.style),
                }
                for action in card.actions
            ]

        if card.context:
            openclaw_card["context"] = card.context

        return openclaw_card

    def _map_action_style(self, style: CardActionStyle) -> str:
        """将 CardActionStyle 映射为 OpenClaw 按钮样式"""
        return style.value
