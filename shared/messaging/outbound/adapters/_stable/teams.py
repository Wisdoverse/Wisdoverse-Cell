"""Microsoft Teams channel adapter using botbuilder.core."""
import asyncio
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity, ActivityTypes

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


class TeamsAdapter(BaseChannelAdapter):
    """Microsoft Teams channel adapter."""

    channel_id = "teams"
    channel_name = "Microsoft Teams"
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

    def __init__(self, app_id: str, app_password: str):
        self._app_id = app_id
        self._app_password = app_password
        self._bot_adapter: BotFrameworkAdapter | None = None
        self._message_queue: list[InboundMessage] = []
        self._turn_contexts: dict[str, TurnContext] = {}  # chat_id -> TurnContext
        self._activity_cache: dict[str, dict[str, Any]] = {}  # message_id -> activity info

    async def connect(self) -> None:
        """Initialize Teams bot adapter."""
        settings = BotFrameworkAdapterSettings(
            app_id=self._app_id,
            app_password=self._app_password,
        )
        self._bot_adapter = BotFrameworkAdapter(settings)
        logger.info("teams_adapter_connected")

    async def disconnect(self) -> None:
        """Shutdown Teams bot adapter."""
        self._bot_adapter = None
        self._turn_contexts.clear()
        self._activity_cache.clear()
        logger.info("teams_adapter_disconnected")

    async def send_message(self, message: OutboundMessage) -> DeliveryResult:
        """Send message via Teams."""
        if not self._bot_adapter:
            return DeliveryResult(
                success=False,
                error_code="NOT_CONNECTED",
                error_message="Bot not connected",
            )

        turn_context = self._turn_contexts.get(message.target_chat_id)
        if not turn_context:
            return DeliveryResult(
                success=False,
                error_code="NO_TURN_CONTEXT",
                error_message="No active conversation context for this chat",
            )

        try:
            # Build activity
            activity = Activity(
                type=ActivityTypes.message,
                text=message.content,
            )

            # Send message
            response = await turn_context.send_activity(activity)

            # Cache activity info for edit/delete
            if response and response.id:
                self._activity_cache[response.id] = {
                    "chat_id": message.target_chat_id,
                    "activity_id": response.id,
                }

            return DeliveryResult(
                success=True,
                platform_message_id=response.id if response else None,
                delivered_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("teams_send_failed", error=str(e))
            return DeliveryResult(
                success=False,
                error_code="SEND_FAILED",
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
        if not self._bot_adapter:
            return False

        activity_info = self._activity_cache.get(message_id)
        if not activity_info:
            return False

        chat_id = activity_info["chat_id"]
        turn_context = self._turn_contexts.get(chat_id)
        if not turn_context:
            return False

        try:
            updated_activity = Activity(
                type=ActivityTypes.message,
                id=message_id,
                text=new_content,
            )
            await turn_context.update_activity(updated_activity)
            return True
        except Exception as e:
            logger.error("teams_edit_failed", error=str(e))
            return False

    async def delete_message(self, message_id: str) -> bool:
        """Delete a sent message."""
        if not self._bot_adapter:
            return False

        activity_info = self._activity_cache.get(message_id)
        if not activity_info:
            return False

        chat_id = activity_info["chat_id"]
        turn_context = self._turn_contexts.get(chat_id)
        if not turn_context:
            return False

        try:
            await turn_context.delete_activity(message_id)
            return True
        except Exception as e:
            logger.error("teams_delete_failed", error=str(e))
            return False

    async def send_typing_indicator(self, chat_id: str) -> None:
        """Send typing indicator."""
        turn_context = self._turn_contexts.get(chat_id)
        if turn_context:
            typing_activity = Activity(type=ActivityTypes.typing)
            await turn_context.send_activity(typing_activity)

    def store_turn_context(self, chat_id: str, turn_context: TurnContext) -> None:
        """Store a turn context for proactive messaging."""
        self._turn_contexts[chat_id] = turn_context

    async def process_activity(
        self, activity: Activity, auth_header: str
    ) -> InboundMessage | None:
        """Process incoming activity from Teams webhook."""
        if not self._bot_adapter:
            return None

        inbound_message: InboundMessage | None = None

        async def on_message(turn_context: TurnContext):
            nonlocal inbound_message

            # Store turn context for replies
            chat_id = turn_context.activity.conversation.id
            self.store_turn_context(chat_id, turn_context)

            # Convert to InboundMessage
            activity = turn_context.activity
            if activity.type == ActivityTypes.message:
                inbound_message = InboundMessage(
                    channel_id=self.channel_id,
                    platform_message_id=activity.id,
                    author=MessageAuthor(
                        platform_user_id=activity.from_property.id,
                        display_name=activity.from_property.name,
                    ),
                    chat=ChatContext(
                        platform_chat_id=activity.conversation.id,
                        chat_type=ChatType.GROUP
                        if activity.conversation.is_group
                        else ChatType.DM,
                        chat_name=activity.conversation.name,
                    ),
                    content=activity.text,
                    raw_payload=activity.as_dict(),
                )

        await self._bot_adapter.process_activity(activity, auth_header, on_message)
        return inbound_message
