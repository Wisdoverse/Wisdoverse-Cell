"""
OpenClawPlatformAdapter - OpenClaw platform adapter.

Implements BasePlatformAdapter for the unified gateway OpenClaw integration.
Converts OpenClaw Gateway events to UnifiedMessage and sends responses through
the gateway.
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
    OpenClaw platform adapter.

    Communicates with OpenClaw Gateway through OpenClawClient and translates
    between OpenClaw events and the unified gateway model.
    """

    def __init__(self, client: OpenClawClient):
        self._client = client
        self._user_cache: dict[str, dict] = {}

    @property
    def platform(self) -> Platform:
        return Platform.OPENCLAW

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        Convert an inbound OpenClaw message event to the unified format.

        Expected raw_event structure:
        {
            "message_id": "...",
            "channel": "whatsapp",  # Original platform.
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

        # Map message type to the unified model.
        raw_type = raw_event.get("message_type", "text")
        message_type = _MSG_TYPE_MAP.get(raw_type, MessageType.TEXT)

        # Normalize the timestamp.
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
        Convert an OpenClaw card callback to the unified format.

        Expected raw_callback structure:
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
        Send a card message through OpenClaw Gateway.

        Args:
            chat_id: Conversation ID.
            card: Unified card model.

        Returns:
            Message ID.
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
        Send a text message through OpenClaw Gateway.

        Args:
            chat_id: Conversation ID.
            text: Message text.

        Returns:
            Message ID.
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
        Update a sent card through OpenClaw Gateway.

        Args:
            message_id: Message ID.
            card: Replacement card content.

        Returns:
            Whether the update succeeded.
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
        Get a user email through OpenClaw Gateway.

        Args:
            platform_user_id: OpenClaw user ID.

        Returns:
            Email address or None.
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("email")

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        Get a user display name through OpenClaw Gateway.

        Args:
            platform_user_id: OpenClaw user ID.

        Returns:
            User name or None.
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("name")

    # === Private Methods ===

    async def _get_user_info(self, user_id: str) -> dict:
        """Get user information with an in-memory cache."""
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
        Convert UnifiedCard to the OpenClaw card format.

        Args:
            card: Unified card model.

        Returns:
            OpenClaw card JSON.
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
        """Map CardActionStyle to the OpenClaw button style."""
        return style.value
