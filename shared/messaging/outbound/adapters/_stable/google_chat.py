"""Google Chat channel adapter using Google Chat API."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
    MediaType,
)
from shared.messaging.outbound.models.messages import (
    DeliveryResult,
    InboundMessage,
    MediaAttachment,
    OutboundMessage,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/chat.bot"]


class GoogleChatAdapter(BaseChannelAdapter):
    """Google Chat channel adapter."""

    channel_id = "google_chat"
    channel_name = "Google Chat"
    status = ChannelStatus.STABLE
    capabilities = {
        ChannelCapability.TEXT,
        ChannelCapability.RICH_MEDIA,
        ChannelCapability.EDIT_MESSAGE,
        ChannelCapability.DELETE_MESSAGE,
        ChannelCapability.GROUP_MANAGEMENT,
        ChannelCapability.WEBHOOKS,
    }

    def __init__(self, credentials_path: str):
        self._credentials_path = credentials_path
        self._client = None
        self._message_queue: list[InboundMessage] = []

    async def connect(self) -> None:
        """Initialize Google Chat client."""
        credentials = service_account.Credentials.from_service_account_file(
            self._credentials_path, scopes=SCOPES
        )
        self._client = build("chat", "v1", credentials=credentials)
        logger.info("google_chat_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Google Chat client."""
        self._client = None
        logger.info("google_chat_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Google Chat."""
        if not self._client:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="Client not connected",
            )

        try:
            body = {"text": message.content}

            # Handle rich media attachments as cards
            if message.attachments:
                cards = self._build_cards(message.attachments)
                if cards:
                    body["cardsV2"] = cards

            result = (
                self._client.spaces()
                .messages()
                .create(parent=message.target_chat_id, body=body)
                .execute()
            )

            return DeliveryResult(
                success=True,
                platform_message_id=result.get("name"),
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("google_chat_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    def _build_cards(
        self, attachments: list[MediaAttachment]
    ) -> list[dict] | None:
        """Build Google Chat cards from attachments."""
        if not attachments:
            return None

        widgets = []
        for attachment in attachments:
            url = attachment.url or attachment.local_path
            if not url:
                continue

            if attachment.media_type == MediaType.IMAGE:
                widgets.append(
                    {"image": {"imageUrl": url, "altText": attachment.file_name or ""}}
                )
            else:
                # Other media types as decorated text with link
                widgets.append(
                    {
                        "decoratedText": {
                            "text": attachment.file_name or "Attachment",
                            "button": {
                                "text": "Download",
                                "onClick": {"openLink": {"url": url}},
                            },
                        }
                    }
                )

        if not widgets:
            return None

        return [
            {
                "cardId": "attachment_card",
                "card": {"sections": [{"widgets": widgets}]},
            }
        ]

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """Listen for incoming messages (webhook mode typically used)."""
        while True:
            if self._message_queue:
                yield self._message_queue.pop(0)
            else:
                await asyncio.sleep(0.1)

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Edit an existing message."""
        if not self._client:
            return False

        try:
            self._client.spaces().messages().update(
                name=message_id,
                updateMask="text",
                body={"text": new_content},
            ).execute()
            return True
        except Exception as e:
            logger.error("google_chat_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a message."""
        if not self._client:
            return False

        try:
            self._client.spaces().messages().delete(name=message_id).execute()
            return True
        except Exception as e:
            logger.error("google_chat_delete_failed", error=str(e))
            return False
