# shared/integrations/wecom/platform_adapter.py
"""
WecomPlatformAdapter - WeCom platform adapter.

Implements BasePlatformAdapter for the unified gateway WeCom integration.
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
    WeCom platform adapter.

    Converts WeCom messages and callbacks to the unified format, and sends
    unified messages back in WeCom format.
    """

    def __init__(self, client: "WecomClient"):
        self._client = client
        self._user_cache: dict[str, dict] = {}

    @property
    def platform(self) -> Platform:
        return Platform.WECOM

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        """
        Convert a WeCom message event to the unified format.

        WeCom message callbacks are XML at the platform boundary and are passed
        here after parsing.

        Args:
            raw_event: Parsed message data converted from XML.

        Returns:
            UnifiedMessage or None.
        """
        # WeCom messages can be passed as an XML Element or a dict.
        if isinstance(raw_event, ET.Element):
            raw_event = self._xml_to_dict(raw_event)

        msg_type = raw_event.get("MsgType", "text")
        user_id = raw_event.get("FromUserName", "")
        msg_id = raw_event.get("MsgId", "")

        if not user_id:
            return None

        # Message content.
        content, unified_type, attachments = self._parse_content(msg_type, raw_event)

        # Event timestamp.
        create_time = raw_event.get("CreateTime", "")
        timestamp = self._parse_timestamp(create_time)

        return UnifiedMessage(
            platform=Platform.WECOM,
            message_id=msg_id or f"wecom_{int(timestamp.timestamp())}",
            chat_id=user_id,  # For WeCom direct messages, chat_id is the user ID.
            chat_type="private",  # WeCom app messages are private by default.
            sender_id=user_id,
            sender_name="",  # Filled by the gateway through UserService.
            message_type=unified_type,
            content=content,
            mentions=[],
            attachments=attachments,
            timestamp=timestamp,
            raw_data=raw_event,
        )

    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        """
        Convert a WeCom card callback to the unified format.

        Args:
            raw_callback: WeCom card callback data.

        Returns:
            UnifiedAction or None.
        """
        # WeCom card callback format:
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

        # Parse EventKey. It can be "action_id" or "action_id:payload_json".
        action_id, value = self._parse_event_key(event_key)

        return UnifiedAction(
            platform=Platform.WECOM,
            action_id=action_id,
            message_id=response_code,  # Used to update the card.
            operator_id=operator_id,
            value=value,
            raw_data=raw_callback,
        )

    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        """
        Send a card message.

        Args:
            chat_id: User ID.
            card: Unified card model.

        Returns:
            Message ID.
        """
        wecom_card = self._build_wecom_card(card)
        return await self._client.send_template_card(chat_id, wecom_card)

    async def send_text(self, chat_id: str, text: str) -> str:
        """
        Send a text message.

        Args:
            chat_id: User ID.
            text: Message text.

        Returns:
            Message ID.
        """
        return await self._client.send_text_message(chat_id, text)

    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        """
        Update a sent card.

        Args:
            message_id: response_code used by WeCom card updates.
            card: Replacement card content.

        Returns:
            Whether the update succeeded.
        """
        wecom_card = self._build_wecom_card(card)
        return await self._client.update_template_card(message_id, wecom_card)

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        """
        Get a user email.

        Args:
            platform_user_id: WeCom UserID.

        Returns:
            Email address or None.
        """
        user_info = await self._get_user_info(platform_user_id)
        return user_info.get("email") or None

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        """
        Get a user display name.

        Args:
            platform_user_id: WeCom UserID.

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

        user_info = await self._client.get_user_info(user_id)
        self._user_cache[user_id] = user_info
        return user_info

    def _xml_to_dict(self, root: ET.Element) -> dict:
        """Convert an XML Element to a dictionary."""
        result = {}
        for child in root:
            result[child.tag] = child.text or ""
        return result

    def _parse_content(
        self, msg_type: str, raw_event: dict
    ) -> tuple[str, MessageType, list[dict]]:
        """
        Parse message content.

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
        """Parse a WeCom timestamp in seconds."""
        if not timestamp_str:
            return datetime.now(UTC)

        try:
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (ValueError, TypeError):
            return datetime.now(UTC)

    def _parse_event_key(self, event_key: str) -> tuple[str, dict]:
        """
        Parse EventKey.

        Supported formats:
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
        Convert UnifiedCard to the WeCom template card format.

        Args:
            card: Unified card model.

        Returns:
            WeCom template card dictionary.
        """
        builder = WecomCardBuilder()

        # Title.
        title = card.title
        if card.status:
            title = f"[{card.status}] {title}"
        builder.set_title(title)

        # Description. WeCom template cards limit this field length.
        description = card.content[:128] if card.content else ""
        if len(card.content) > 128:
            description += "..."
        builder.set_description(description)

        # Fields.
        for field in card.fields[:6]:  # WeCom supports up to six fields.
            builder.add_horizontal_content(
                key=field.get("label", ""),
                value=field.get("value", ""),
            )

        # Buttons.
        for action in card.actions[:2]:
            style = self._map_action_style(action.style)

            # Build a key that carries action_id and callback value.
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
        Map CardActionStyle to a WeCom button style.

        WeCom styles: 1=blue, 2=gray, 3=red.
        """
        style_map = {
            CardActionStyle.PRIMARY: 1,
            CardActionStyle.DEFAULT: 2,
            CardActionStyle.DANGER: 3,
        }
        return style_map.get(style, 2)
