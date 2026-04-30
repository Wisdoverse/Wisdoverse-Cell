"""Matrix channel adapter using matrix-nio library."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

import nio

from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
    MediaType,
    ParseMode,
)
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    MediaAttachment,
    OutboundMessage,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class MatrixAdapter(BaseChannelAdapter):
    """Matrix channel adapter."""

    channel_id = "matrix"
    channel_name = "Matrix"
    status = ChannelStatus.STABLE
    capabilities = {
        ChannelCapability.TEXT,
        ChannelCapability.RICH_MEDIA,
        ChannelCapability.EDIT_MESSAGE,
        ChannelCapability.DELETE_MESSAGE,
        ChannelCapability.REACTIONS,
        ChannelCapability.READ_RECEIPTS,
        ChannelCapability.TYPING_INDICATOR,
        ChannelCapability.GROUP_MANAGEMENT,
        ChannelCapability.WEBHOOKS,
    }

    def __init__(self, homeserver: str, user_id: str, access_token: str):
        self._homeserver = homeserver
        self._user_id = user_id
        self._access_token = access_token
        self._client: nio.AsyncClient | None = None
        self._message_queue: list[InboundMessage] = []
        self._room_id_cache: dict[str, str] = {}  # event_id -> room_id

    async def connect(self) -> None:
        """Initialize Matrix client."""
        self._client = nio.AsyncClient(
            homeserver=self._homeserver,
            user=self._user_id,
        )
        self._client.access_token = self._access_token
        logger.info("matrix_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Matrix client."""
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("matrix_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Matrix."""
        if not self._client:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="Client not connected",
            )

        try:
            # Build message content
            content = {
                "msgtype": "m.text",
                "body": message.content or "",
            }

            # Handle formatted content
            if message.parse_mode == ParseMode.HTML:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = message.content
            elif message.parse_mode == ParseMode.MARKDOWN:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = message.content

            # Handle reply
            if message.reply_to_platform_message_id:
                content["m.relates_to"] = {
                    "m.in_reply_to": {
                        "event_id": message.reply_to_platform_message_id,
                    }
                }

            # Send text message
            if message.content:
                response = await self._client.room_send(
                    room_id=message.target_chat_id,
                    message_type="m.room.message",
                    content=content,
                )

                if hasattr(response, "event_id"):
                    event_id = response.event_id
                    self._room_id_cache[event_id] = message.target_chat_id

                    return DeliveryResult(
                        success=True,
                        platform_message_id=event_id,
                        delivered_at=datetime.now(UTC),
                    )

            # Send media attachments
            for attachment in message.attachments:
                result = await self._send_media(message.target_chat_id, attachment)
                if not result.success:
                    return result

            return DeliveryResult(
                success=True,
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("matrix_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    async def _send_media(
        self, room_id: str, attachment: MediaAttachment
    ) -> DeliveryResult:
        """Send media attachment."""
        if not self._client:
            return DeliveryResult(success=False, error_code="NOT_CONNECTED")

        try:
            url = attachment.url or attachment.local_path
            if not url:
                return DeliveryResult(success=False, error_code="NO_MEDIA_URL")

            # Map media types to Matrix message types
            msgtype_map = {
                MediaType.IMAGE: "m.image",
                MediaType.VIDEO: "m.video",
                MediaType.AUDIO: "m.audio",
                MediaType.VOICE: "m.audio",
                MediaType.FILE: "m.file",
            }

            msgtype = msgtype_map.get(attachment.media_type, "m.file")

            content = {
                "msgtype": msgtype,
                "body": attachment.file_name or "attachment",
                "url": url,
            }

            if attachment.mime_type:
                content["info"] = {"mimetype": attachment.mime_type}

            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )

            return DeliveryResult(success=True, delivered_at=datetime.now(UTC))

        except Exception as e:
            return DeliveryResult(
                success=False,
                error_code="MEDIA_SEND_FAILED",
                error_message=str(e),
            )

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """Listen for incoming messages."""
        while True:
            if self._message_queue:
                yield self._message_queue.pop(0)
            else:
                await asyncio.sleep(0.1)

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Edit a sent message by sending a replacement event."""
        if not self._client:
            return False

        room_id = self._room_id_cache.get(message_id)
        if not room_id:
            return False

        try:
            content = {
                "msgtype": "m.text",
                "body": f"* {new_content}",
                "m.new_content": {
                    "msgtype": "m.text",
                    "body": new_content,
                },
                "m.relates_to": {
                    "rel_type": "m.replace",
                    "event_id": message_id,
                },
            }

            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )
            return True
        except Exception as e:
            logger.error("matrix_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a sent message by redacting it."""
        if not self._client:
            return False

        room_id = self._room_id_cache.get(message_id)
        if not room_id:
            return False

        try:
            await self._client.room_redact(
                room_id=room_id,
                event_id=message_id,
            )
            return True
        except Exception as e:
            logger.error("matrix_delete_failed", error=str(e))
            return False

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator."""
        if self._client:
            await self._client.room_typing(room_id=chat_id, typing_state=True)

    async def add_reaction(self, message_id: str, emoji: str) -> bool:
        """Add reaction to a message."""
        if not self._client:
            return False

        room_id = self._room_id_cache.get(message_id)
        if not room_id:
            return False

        try:
            content = {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": message_id,
                    "key": emoji,
                }
            }
            await self._client.room_send(
                room_id=room_id,
                message_type="m.reaction",
                content=content,
            )
            return True
        except Exception as e:
            logger.error("matrix_reaction_failed", error=str(e))
            return False

    async def mark_as_read(self, message_id: str) -> None:
        """Mark message as read."""
        if not self._client:
            return

        room_id = self._room_id_cache.get(message_id)
        if not room_id:
            return

        try:
            await self._client.room_read_markers(
                room_id=room_id,
                fully_read_event=message_id,
                read_event=message_id,
            )
        except Exception as e:
            logger.error("matrix_read_marker_failed", error=str(e))
