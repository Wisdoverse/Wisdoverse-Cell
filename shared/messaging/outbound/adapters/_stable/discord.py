"""Discord channel adapter using discord.py."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

import discord

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


class DiscordAdapter(BaseChannelAdapter):
    """Discord channel adapter."""

    channel_id = "discord"
    channel_name = "Discord"
    status = ChannelStatus.STABLE
    capabilities = {
        ChannelCapability.TEXT,
        ChannelCapability.RICH_MEDIA,
        ChannelCapability.EDIT_MESSAGE,
        ChannelCapability.DELETE_MESSAGE,
        ChannelCapability.REACTIONS,
        ChannelCapability.TYPING_INDICATOR,
        ChannelCapability.GROUP_MANAGEMENT,
        ChannelCapability.WEBHOOKS,
        # Note: Discord does NOT support READ_RECEIPTS
    }

    def __init__(self, token: str):
        self._token = token
        self._client: discord.Client | None = None
        self._message_queue: list[InboundMessage] = []
        self._channel_id_cache: dict[str, str] = {}  # message_id -> channel_id

    async def connect(self) -> None:
        """Initialize Discord client."""
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        logger.info("discord_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Discord client."""
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("discord_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Discord."""
        if not self._client:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="Client not connected",
            )

        try:
            channel = self._client.get_channel(int(message.target_chat_id))
            if not channel:
                return DeliveryResult(
                    success=False,
                    error_code="CHANNEL_NOT_FOUND",
                    error_message=f"Channel {message.target_chat_id} not found",
                )

            # Send text message
            if message.content:
                result = await channel.send(content=message.content)

                # Cache channel_id for edit/delete
                msg_id = str(result.id)
                self._channel_id_cache[msg_id] = message.target_chat_id

                return DeliveryResult(
                    success=True,
                    platform_message_id=msg_id,
                    delivered_at=datetime.now(UTC),
                )

            # Send media attachments
            for attachment in message.attachments:
                result = await self._send_media(channel, attachment)
                if not result.success:
                    return result

            return DeliveryResult(
                success=True,
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("discord_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    async def _send_media(
        self, channel, attachment: MediaAttachment
    ) -> DeliveryResult:
        """Send media attachment."""
        try:
            url = attachment.url or attachment.local_path
            if not url:
                return DeliveryResult(
                    success=False, error_code="NO_MEDIA_URL"
                )

            # Discord sends files as attachments to messages
            await channel.send(content=url)

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
        if not self._client:
            return False

        channel_id = self._channel_id_cache.get(message_id)
        if not channel_id:
            return False

        try:
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                return False

            message = await channel.fetch_message(int(message_id))
            await message.edit(content=new_content)
            return True
        except Exception as e:
            logger.error("discord_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a sent message."""
        if not self._client:
            return False

        channel_id = self._channel_id_cache.get(message_id)
        if not channel_id:
            return False

        try:
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                return False

            message = await channel.fetch_message(int(message_id))
            await message.delete()
            return True
        except Exception as e:
            logger.error("discord_delete_failed", error=str(e))
            return False

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator."""
        if self._client:
            channel = self._client.get_channel(int(chat_id))
            if channel:
                await channel.typing()
