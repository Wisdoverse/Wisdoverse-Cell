"""Telegram channel adapter using python-telegram-bot."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

from telegram import Bot

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


class TelegramAdapter(BaseChannelAdapter):
    """Telegram channel adapter."""

    channel_id = "telegram"
    channel_name = "Telegram"
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
        self._bot: Bot | None = None
        self._message_queue: list[InboundMessage] = []
        self._chat_id_cache: dict[str, str] = {}  # message_id -> chat_id

    async def connect(self) -> None:
        """Initialize Telegram bot."""
        self._bot = Bot(token=self._token)
        logger.info("telegram_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Telegram bot."""
        if self._bot:
            await self._bot.shutdown()
            self._bot = None
        logger.info("telegram_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Telegram."""
        if not self._bot:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="Bot not connected",
            )

        try:
            # Determine parse mode
            parse_mode = None
            if message.parse_mode == ParseMode.MARKDOWN:
                parse_mode = "MarkdownV2"
            elif message.parse_mode == ParseMode.HTML:
                parse_mode = "HTML"

            # Send text message
            if message.content:
                result = await self._bot.send_message(
                    chat_id=message.target_chat_id,
                    text=message.content,
                    parse_mode=parse_mode,
                    disable_notification=message.silent,
                    reply_to_message_id=(
                        int(message.reply_to_platform_message_id)
                        if message.reply_to_platform_message_id
                        else None
                    ),
                )

                # Cache chat_id for edit/delete
                msg_id = str(result.message_id)
                self._chat_id_cache[msg_id] = message.target_chat_id

                return DeliveryResult(
                    success=True,
                    platform_message_id=msg_id,
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
            logger.error("telegram_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    async def _send_media(
        self, chat_id: str, attachment: MediaAttachment
    ) -> DeliveryResult:
        """Send media attachment."""
        if not self._bot:
            return DeliveryResult(success=False, error_code="NOT_CONNECTED")

        try:
            url = attachment.url or attachment.local_path
            if not url:
                return DeliveryResult(
                    success=False, error_code="NO_MEDIA_URL"
                )

            if attachment.media_type == MediaType.IMAGE:
                await self._bot.send_photo(chat_id=chat_id, photo=url)
            elif attachment.media_type == MediaType.VIDEO:
                await self._bot.send_video(chat_id=chat_id, video=url)
            elif attachment.media_type == MediaType.AUDIO:
                await self._bot.send_audio(chat_id=chat_id, audio=url)
            elif attachment.media_type == MediaType.VOICE:
                await self._bot.send_voice(chat_id=chat_id, voice=url)
            elif attachment.media_type == MediaType.FILE:
                await self._bot.send_document(chat_id=chat_id, document=url)
            elif attachment.media_type == MediaType.STICKER:
                await self._bot.send_sticker(chat_id=chat_id, sticker=url)

            return DeliveryResult(success=True, delivered_at=datetime.now(UTC))

        except Exception as e:
            return DeliveryResult(
                success=False,
                error_code="MEDIA_SEND_FAILED",
                error_message=str(e),
            )

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """Listen for incoming messages (polling mode)."""
        while True:
            if self._message_queue:
                yield self._message_queue.pop(0)
            else:
                await asyncio.sleep(0.1)

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Edit a sent message."""
        if not self._bot:
            return False

        chat_id = self._chat_id_cache.get(message_id)
        if not chat_id:
            return False

        try:
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(message_id),
                text=new_content,
            )
            return True
        except Exception as e:
            logger.error("telegram_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a sent message."""
        if not self._bot:
            return False

        chat_id = self._chat_id_cache.get(message_id)
        if not chat_id:
            return False

        try:
            await self._bot.delete_message(
                chat_id=chat_id,
                message_id=int(message_id),
            )
            return True
        except Exception as e:
            logger.error("telegram_delete_failed", error=str(e))
            return False

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator."""
        if self._bot:
            await self._bot.send_chat_action(chat_id=chat_id, action="typing")
