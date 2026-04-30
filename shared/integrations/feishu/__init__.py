"""
Feishu Gateway - 飞书深度集成模块

统一管理飞书 API 调用、事件订阅、Bot 消息、卡片回调。

使用方式:
    from shared.integrations.feishu import init_feishu_gateway, feishu_client

    # 在应用启动时初始化
    await init_feishu_gateway(agent)

    # 使用客户端
    client = feishu_client()
    await client.send_card(...)
"""
from typing import Optional

from shared.config import settings
from shared.utils.logger import get_logger

from .client import FeishuClient, feishu_client, get_feishu_client
from .errors import (
    FeishuAPIError,
    feishu_error_handler,
    handle_feishu_response,
    retryable_request,
)
from .handlers.bot import BotHandler
from .handlers.card import CardHandler
from .handlers.event import EventHandler
from .handlers.message import MessageRecorder
from .platform_adapter import FeishuPlatformAdapter
from .router import init_handlers, router
from .services.session_manager import SessionManager

logger = get_logger("feishu")

# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> Optional[SessionManager]:
    """Get the global session manager instance"""
    return _session_manager

__all__ = [
    "FeishuClient",
    "feishu_client",
    "get_feishu_client",
    "get_session_manager",
    "router",
    "init_feishu_gateway",
    "EventHandler",
    "BotHandler",
    "CardHandler",
    "MessageRecorder",
    "SessionManager",
    # Platform adapter for unified gateway
    "FeishuPlatformAdapter",
    # Error handling
    "FeishuAPIError",
    "feishu_error_handler",
    "handle_feishu_response",
    "retryable_request",
]


async def init_feishu_gateway(agent, db=None, redis=None, pm_client=None) -> bool:
    """
    初始化飞书网关

    Args:
        agent: RequirementManagerAgent 实例
        db: DatabaseManager (optional, for message recording)
        redis: Redis client (optional, for session management)

    Returns:
        是否初始化成功
    """
    if not settings.feishu_enabled:
        logger.info("feishu_gateway_disabled")
        return False

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        logger.warning("feishu_credentials_not_configured")
        return False

    # Get client instance
    client = get_feishu_client()

    # Verify credentials
    try:
        await client.get_access_token()
        logger.info("feishu_credentials_verified")
    except Exception as e:
        logger.error("feishu_auth_failed", error=str(e))
        return False

    # Initialize handlers
    event_handler = EventHandler(client, agent)
    bot_handler = BotHandler(client, agent)
    card_handler = CardHandler(client, agent, pm_client=pm_client)

    # Initialize message recording if enabled
    global _session_manager
    message_recorder = None
    if settings.feishu_message_recording_enabled and db and redis:
        _session_manager = SessionManager(redis=redis, db=db, agent=agent)
        message_recorder = MessageRecorder(
            feishu_client=client,
            db=db,
            session_manager=_session_manager,
        )
        logger.info("message_recording_initialized")

    # Register handlers with router
    init_handlers(event_handler, bot_handler, card_handler, message_recorder)

    logger.info("feishu_gateway_initialized")
    return True
