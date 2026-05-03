# shared/services/gateway/gateway.py
"""
UnifiedGateway - 统一消息网关

协调各平台适配器与 Agent 的消息流转。
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

# Agent 消息处理函数类型
MessageHandler = Callable[[UnifiedMessage], Coroutine[Any, Any, Optional[AgentResponse]]]
ActionHandler = Callable[[UnifiedAction], Coroutine[Any, Any, Optional[ActionResponse]]]


class UnifiedGateway:
    """
    统一消息网关

    职责：
    1. 消息路由：平台消息 → Agent
    2. 响应分发：Agent 响应 → 平台
    3. 用户映射：平台 ID → 统一用户
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
            user_service: 用户服务
            adapters: 平台适配器字典
            message_handler: 消息处理函数（由 Agent 提供）
            action_handler: 回调处理函数（由 Agent 提供）
            skill_service: 技能服务（可选，用于命令/模式匹配）
        """
        self.user_service = user_service
        self.adapters: dict[Platform, BasePlatformAdapter] = adapters or {}
        self._message_handler = message_handler
        self._action_handler = action_handler
        self._skill_service = skill_service

        # 将适配器传给 UserService
        if adapters:
            user_service.set_adapters(adapters)

    def register_adapter(self, adapter: BasePlatformAdapter) -> None:
        """注册平台适配器"""
        self.adapters[adapter.platform] = adapter
        self.user_service.set_adapters(self.adapters)
        logger.info("adapter_registered", platform=adapter.platform.value)

    def set_message_handler(self, handler: MessageHandler) -> None:
        """设置消息处理函数"""
        self._message_handler = handler

    def set_action_handler(self, handler: ActionHandler) -> None:
        """设置回调处理函数"""
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
        处理入站消息

        流程：
        1. 获取适配器
        2. 解析为统一格式
        3. 用户身份映射
        4. 交给 Agent 处理
        5. 发送响应

        Args:
            platform: 平台类型
            raw_event: 平台原始事件数据
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return

        # 1. 解析为统一格式
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

        # 2. 用户身份映射
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
            # 继续处理，但没有用户映射

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

        # 5. 发送响应
        if response:
            await self._send_response(adapter, message.chat_id, response)

    async def handle_action(
        self,
        platform: Platform,
        raw_callback: dict,
    ) -> Optional[dict]:
        """
        处理卡片回调

        Args:
            platform: 平台类型
            raw_callback: 平台回调数据

        Returns:
            响应数据（用于同步返回给平台）
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            logger.warning("unknown_platform", platform=platform.value)
            return None

        # 1. 解析回调
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

        # 2. 用户身份映射
        try:
            user = await self.user_service.resolve_user(platform, action.operator_id)
            action.user_id = user.id
        except Exception as e:
            logger.warning("user_resolve_failed", error=str(e), operator_id=action.operator_id)

        # 3. 交给 Agent 处理
        if not self._action_handler:
            logger.warning("no_action_handler")
            return None

        try:
            response = await self._action_handler(action)
        except Exception as e:
            logger.error("action_handler_error", error=str(e))
            return {"toast": {"type": "error", "content": f"处理失败: {str(e)}"}}

        # 4. 更新卡片或返回响应
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
        主动发送卡片

        Args:
            platform: 目标平台
            chat_id: 会话 ID
            card: 卡片内容

        Returns:
            消息 ID 或 None
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
        主动发送文本

        Args:
            platform: 目标平台
            chat_id: 会话 ID
            text: 文本内容

        Returns:
            消息 ID 或 None
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
        """发送 Agent 响应"""
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
        """处理 Action 响应"""
        result: dict = {}

        # 更新卡片
        if response.update_card and response.card and action.message_id:
            try:
                await adapter.update_card(action.message_id, response.card)
                result["card"] = self._convert_card_to_platform(adapter, response.card)
            except Exception as e:
                logger.error("update_card_error", error=str(e))

        # Toast 消息
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
        转换卡片为平台格式

        用于同步返回给平台（如飞书卡片回调响应）。
        """
        # 这里需要调用 adapter 的内部方法，但为了保持封装，
        # 我们让 adapter 自己处理
        if hasattr(adapter, "_build_feishu_card"):
            return adapter._build_feishu_card(card)
        elif hasattr(adapter, "_build_wecom_card"):
            return adapter._build_wecom_card(card)
        return {}
