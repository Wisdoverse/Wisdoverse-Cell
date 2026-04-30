"""Slack channel adapter using slack_bolt."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

from slack_bolt.async_app import AsyncApp

from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
)
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    MediaAttachment,
    OutboundMessage,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SlackAdapter(BaseChannelAdapter):
    """Slack channel adapter."""

    channel_id = "slack"
    channel_name = "Slack"
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

    def __init__(self, token: str):
        self._token = token
        self._app: AsyncApp | None = None
        self._message_queue: list[InboundMessage] = []
        self._channel_cache: dict[str, str] = {}  # message_ts -> channel_id

    async def connect(self) -> None:
        """Initialize Slack app."""
        self._app = AsyncApp(token=self._token)
        logger.info("slack_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Slack app."""
        if self._app:
            self._app = None
        logger.info("slack_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Slack."""
        if not self._app:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="App not connected",
            )

        try:
            # Send text message
            if message.content:
                result = await self._app.client.chat_postMessage(
                    channel=message.target_chat_id,
                    text=message.content,
                    thread_ts=(
                        message.reply_to_platform_message_id
                        if message.reply_to_platform_message_id
                        else None
                    ),
                )

                # Cache channel_id for edit/delete
                msg_ts = result.get("ts")
                if msg_ts:
                    self._channel_cache[msg_ts] = message.target_chat_id

                return DeliveryResult(
                    success=True,
                    platform_message_id=msg_ts,
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
            logger.error("slack_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    async def _send_media(
        self, channel_id: str, attachment: MediaAttachment
    ) -> DeliveryResult:
        """Send media attachment."""
        if not self._app:
            return DeliveryResult(success=False, error_code="NOT_CONNECTED")

        try:
            file_path = attachment.local_path or attachment.url
            if not file_path:
                return DeliveryResult(
                    success=False, error_code="NO_MEDIA_URL"
                )

            await self._app.client.files_upload_v2(
                channel=channel_id,
                file=file_path,
                filename=attachment.file_name,
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
        """Edit a sent message."""
        if not self._app:
            return False

        channel_id = self._channel_cache.get(message_id)
        if not channel_id:
            return False

        try:
            await self._app.client.chat_update(
                channel=channel_id,
                ts=message_id,
                text=new_content,
            )
            return True
        except Exception as e:
            logger.error("slack_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a sent message."""
        if not self._app:
            return False

        channel_id = self._channel_cache.get(message_id)
        if not channel_id:
            return False

        try:
            await self._app.client.chat_delete(
                channel=channel_id,
                ts=message_id,
            )
            return True
        except Exception as e:
            logger.error("slack_delete_failed", error=str(e))
            return False

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator (Slack doesn't support this directly)."""
        # Slack doesn't have a native typing indicator API
        # This is a no-op but maintains interface compatibility
        pass

    async def add_reaction(self, message_id: str, emoji: str) -> bool:
        """Add reaction to a message."""
        if not self._app:
            return False

        channel_id = self._channel_cache.get(message_id)
        if not channel_id:
            return False

        try:
            await self._app.client.reactions_add(
                channel=channel_id,
                timestamp=message_id,
                name=emoji,
            )
            return True
        except Exception as e:
            logger.error("slack_add_reaction_failed", error=str(e))
            return False

    async def remove_reaction(self, message_id: str, emoji: str) -> bool:
        """Remove reaction from a message."""
        if not self._app:
            return False

        channel_id = self._channel_cache.get(message_id)
        if not channel_id:
            return False

        try:
            await self._app.client.reactions_remove(
                channel=channel_id,
                timestamp=message_id,
                name=emoji,
            )
            return True
        except Exception as e:
            logger.error("slack_remove_reaction_failed", error=str(e))
            return False
