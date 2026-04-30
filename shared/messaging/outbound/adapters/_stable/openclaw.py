"""OpenClaw channel adapter for Channel Gateway agent."""
import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

from shared.config import settings
from shared.integrations.openclaw.client import OpenClawClient
from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
    ChatType,
)
from shared.messaging.outbound.models.messages import (
    ChatContext,
    DeliveryResult,
    InboundMessage,
    MessageAuthor,
    OutboundMessage,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class OpenClawAdapter(BaseChannelAdapter):
    """OpenClaw channel adapter using WebSocket JSON-RPC."""

    channel_id = "openclaw"
    channel_name = "OpenClaw"
    status = ChannelStatus.STABLE
    capabilities = {
        ChannelCapability.TEXT,
        ChannelCapability.RICH_MEDIA,
        ChannelCapability.EDIT_MESSAGE,
    }

    def __init__(
        self,
        gateway_url: str | None = None,
        device_id: str | None = None,
        auth_token: str | None = None,
    ):
        self._gateway_url = gateway_url or settings.openclaw_gateway_url
        self._device_id = device_id or settings.openclaw_device_id
        self._auth_token = auth_token or settings.openclaw_gateway_token.get_secret_value()
        self._client: OpenClawClient | None = None
        self._message_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._connect_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Connect to OpenClaw Gateway via WebSocket."""
        self._client = OpenClawClient(
            gateway_url=self._gateway_url,
            device_id=self._device_id,
            auth_token=self._auth_token,
        )
        self._client.on_event(self._on_gateway_event)

        # Run client.connect() as background task (it blocks while connected)
        self._connect_task = asyncio.create_task(self._client.connect())
        logger.info("openclaw_adapter_connecting", gateway_url=self._gateway_url)

    async def disconnect(self) -> None:
        """Disconnect from OpenClaw Gateway."""
        if self._client:
            await self._client.disconnect()
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
        self._client = None
        logger.info("openclaw_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send a message via OpenClaw Gateway."""
        if not self._client or not self._client.connected:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="OpenClaw Gateway not connected",
            )

        try:
            result = await self._client.send_request(
                "channel.sendText",
                params={
                    "chat_id": message.target_chat_id,
                    "text": message.content or "",
                },
            )
            return DeliveryResult(
                success=True,
                platform_message_id=result.get("message_id"),
                delivered_at=datetime.now(UTC),
            )
        except Exception as e:
            logger.error("openclaw_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
                error_message=str(e),
            )

    async def listen(self) -> AsyncIterator[InboundMessage]:
        """Listen for incoming messages from OpenClaw Gateway."""
        while True:
            message = await self._message_queue.get()
            yield message

    async def edit_message(self, message_id: str, new_content: str) -> bool:
        """Edit a sent message via OpenClaw Gateway."""
        if not self._client or not self._client.connected:
            return False

        try:
            result = await self._client.send_request(
                "channel.editMessage",
                params={
                    "message_id": message_id,
                    "content": new_content,
                },
            )
            return result.get("success", False)
        except Exception as e:
            logger.error("openclaw_edit_failed", error=str(e))
            return False

    async def _on_gateway_event(self, method: str, params: dict) -> None:
        """Handle inbound events from OpenClaw Gateway."""
        if method != "channel.message":
            return

        sender = params.get("sender", {})
        chat_id = params.get("chat_id", "")
        chat_type_raw = params.get("chat_type", "private")

        chat_type = ChatType.DM if chat_type_raw == "private" else ChatType.GROUP

        message = InboundMessage(
            channel_id="openclaw",
            platform_message_id=params.get("message_id", ""),
            author=MessageAuthor(
                platform_user_id=sender.get("id", ""),
                display_name=sender.get("name"),
            ),
            chat=ChatContext(
                platform_chat_id=chat_id,
                chat_type=chat_type,
            ),
            content=params.get("content"),
            timestamp=datetime.now(UTC),
            raw_payload=params,
        )
        await self._message_queue.put(message)
