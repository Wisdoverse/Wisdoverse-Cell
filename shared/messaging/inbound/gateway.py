# shared/services/gateway/gateway.py
"""
UnifiedGateway - unified message gateway.

Coordinates message flow between platform adapters and agents.
"""
from typing import Any, Callable, Coroutine, Optional

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .adapter import BasePlatformAdapter
from .models import (
    ActionResponse,
    AgentResponse,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)
from .user_service import UserService

logger = get_logger("gateway")

# Agent message handler function types.
MessageHandler = Callable[[UnifiedMessage], Coroutine[Any, Any, Optional[AgentResponse]]]
ActionHandler = Callable[[UnifiedAction], Coroutine[Any, Any, Optional[ActionResponse]]]


class UnifiedGateway:
    """
    Unified message gateway.

    Responsibilities:
    1. Message routing: platform message -> Agent.
    2. Response dispatch: Agent response -> platform.
    3. User mapping: platform ID -> unified user.
    """

    def __init__(
        self,
        user_service: UserService,
        adapters: Optional[dict[Platform, BasePlatformAdapter]] = None,
        message_handler: Optional[MessageHandler] = None,
        action_handler: Optional[ActionHandler] = None,
        skill_service: Optional[Any] = None,  # SkillService, use Any to avoid circular import
    ):
        """
        Args:
            user_service: User service.
            adapters: Platform adapter dictionary.
            message_handler: Message handler provided by the Agent.
            action_handler: Callback handler provided by the Agent.
            skill_service: Optional skill service for command and pattern matching.
        """
        self.user_service = user_service
        self.adapters: dict[Platform, BasePlatformAdapter] = adapters or {}
        self._message_handler = message_handler
        self._action_handler = action_handler
        self._skill_service = skill_service

        # Pass adapters to UserService.
        if adapters:
            user_service.set_adapters(adapters)

    def register_adapter(self, adapter: BasePlatformAdapter) -> None:
        """Register a platform adapter."""
        self.adapters[adapter.platform] = adapter
        self.user_service.set_adapters(self.adapters)
        logger.info("adapter_registered", platform=adapter.platform.value)

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the message handler."""
        self._message_handler = handler

    def set_action_handler(self, handler: ActionHandler) -> None:
        """Set the callback handler."""
        self._action_handler = handler

    def set_skill_service(self, skill_service: Any) -> None:
        """Set skill service for command/pattern matching"""
        self._skill_service = skill_service

    async def handle_message(
        self,
        platform: Platform,
        raw_event: dict,
    ) -> None:
        """
        Handle an inbound message.

        Flow:
        1. Get adapter.
        2. Parse to unified format.
        3. Resolve user identity.
        4. Pass to Agent.
        5. Send response.

        Args:
            platform: Platform type.
            raw_event: Raw platform event data.
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return

        # 1. Parse to unified format.
        message = await adapter.parse_message(raw_event)
        if not message:
            logger.debug("message_parse_failed", platform=platform.value)
            return

        logger.info(
            "message_received",
            platform=platform.value,
            message_hash=hash_identifier(message.message_id),
            chat_hash=hash_identifier(message.chat_id),
            content_length=len(message.content or ""),
        )

        # 2. Resolve user identity.
        user = None
        try:
            user = await self.user_service.resolve_user(platform, message.sender_id)
            message.user_id = user.id
            message.sender_name = user.name
        except Exception as e:
            logger.warning(
                "user_resolve_failed",
                error=str(e),
                sender_hash=hash_identifier(message.sender_id),
            )
            # Continue processing without user mapping.

        # 3. Try skill handling first
        if self._skill_service:
            result = await self._skill_service.try_handle(message, user)
            if result:
                # Skill handled the message
                return

        # 4. No skill matched, continue with regular handler
        if not self._message_handler:
            logger.warning("no_message_handler")
            return

        try:
            response = await self._message_handler(message)
        except Exception as e:
            logger.error("message_handler_error", error=str(e))
            response = AgentResponse(text=f"处理消息时发生错误: {str(e)}")

        # 5. Send response.
        if response:
            await self._send_response(adapter, message.chat_id, response)

    async def handle_action(
        self,
        platform: Platform,
        raw_callback: dict,
    ) -> Optional[dict]:
        """
        Handle a card callback.

        Args:
            platform: Platform type.
            raw_callback: Platform callback data.

        Returns:
            Response data for synchronous platform callbacks.
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return None

        # 1. Parse callback.
        action = await adapter.parse_action(raw_callback)
        if not action:
            logger.debug("action_parse_failed", platform=platform.value)
            return None

        logger.info(
            "action_received",
            platform=platform.value,
            action_id=action.action_id,
            operator_id=action.operator_id,
        )

        # 2. Resolve user identity.
        try:
            user = await self.user_service.resolve_user(platform, action.operator_id)
            action.user_id = user.id
        except Exception as e:
            logger.warning("user_resolve_failed", error=str(e), operator_id=action.operator_id)

        # 3. Pass to Agent.
        if not self._action_handler:
            logger.warning("no_action_handler")
            return None

        try:
            response = await self._action_handler(action)
        except Exception as e:
            logger.error("action_handler_error", error=str(e))
            return {"toast": {"type": "error", "content": f"处理失败: {str(e)}"}}

        # 4. Update card or return response.
        if response:
            return await self._handle_action_response(adapter, action, response)

        return None

    async def send_card(
        self,
        platform: Platform,
        chat_id: str,
        card: UnifiedCard,
    ) -> Optional[str]:
        """
        Send a card proactively.

        Args:
            platform: Target platform.
            chat_id: Conversation ID.
            card: Card content.

        Returns:
            Message ID or None.
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return None

        try:
            message_id = await adapter.send_card(chat_id, card)
            logger.info(
                "card_sent",
                platform=platform.value,
                chat_hash=hash_identifier(chat_id),
                message_hash=hash_identifier(message_id),
            )
            return message_id
        except Exception as e:
            logger.error("send_card_error", platform=platform.value, error=str(e))
            return None

    async def send_text(
        self,
        platform: Platform,
        chat_id: str,
        text: str,
    ) -> Optional[str]:
        """
        Send text proactively.

        Args:
            platform: Target platform.
            chat_id: Conversation ID.
            text: Message text.

        Returns:
            Message ID or None.
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return None

        try:
            message_id = await adapter.send_text(chat_id, text)
            logger.info(
                "text_sent",
                platform=platform.value,
                chat_hash=hash_identifier(chat_id),
                message_hash=hash_identifier(message_id),
            )
            return message_id
        except Exception as e:
            logger.error("send_text_error", platform=platform.value, error=str(e))
            return None

    # === Private Methods ===

    async def _send_response(
        self,
        adapter: BasePlatformAdapter,
        chat_id: str,
        response: AgentResponse,
    ) -> None:
        """Send an Agent response."""
        try:
            if response.card:
                await adapter.send_card(chat_id, response.card)
            elif response.text:
                await adapter.send_text(chat_id, response.text)
        except Exception as e:
            logger.error(
                "send_response_error",
                error=str(e),
                chat_hash=hash_identifier(chat_id),
            )

    async def _handle_action_response(
        self,
        adapter: BasePlatformAdapter,
        action: UnifiedAction,
        response: ActionResponse,
    ) -> dict:
        """Handle an Action response."""
        result: dict = {}

        # Update card.
        if response.update_card and response.card and action.message_id:
            try:
                await adapter.update_card(action.message_id, response.card)
                result["card"] = self._convert_card_to_platform(adapter, response.card)
            except Exception as e:
                logger.error("update_card_error", error=str(e))

        # Toast message.
        if response.toast:
            result["toast"] = {
                "type": "success",
                "content": response.toast,
            }

        return result

    def _convert_card_to_platform(
        self,
        adapter: BasePlatformAdapter,
        card: UnifiedCard,
    ) -> dict:
        """
        Convert a card to platform-native format.

        Used when returning data synchronously to a platform callback, such as
        Feishu card callbacks.
        """
        # Call the adapter's explicit platform conversion hook when available.
        if hasattr(adapter, "_build_feishu_card"):
            return adapter._build_feishu_card(card)
        elif hasattr(adapter, "_build_wecom_card"):
            return adapter._build_wecom_card(card)
        return {}
