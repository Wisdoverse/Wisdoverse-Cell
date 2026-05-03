"""Requirements-owned Feishu gateway runtime wiring."""

from typing import Optional

from shared.config import settings
from shared.integrations.feishu.client import (
    FeishuClient,
    feishu_client,
    get_feishu_client,
)
from shared.integrations.feishu.router import init_handlers, router
from shared.utils.logger import get_logger

from .bot import BotHandler
from .card import CardHandler
from .event import EventHandler
from .message_recorder import MessageRecorder
from .session_manager import SessionManager

logger = get_logger("requirements.integrations.feishu")

_session_manager: Optional[SessionManager] = None


def get_session_manager() -> Optional[SessionManager]:
    """Get the requirements Feishu session manager instance."""
    return _session_manager


async def init_feishu_gateway(agent, db=None, redis=None, pm_client=None) -> bool:
    """
    Initialize the requirement manager agent Feishu gateway.

    Args:
        agent: RequirementManagerAgent instance.
        db: DatabaseManager, used when message recording is enabled.
        redis: Redis client, used when message recording is enabled.
        pm_client: Project-management typed client for decomposition approvals.

    Returns:
        True when handlers are registered, False when Feishu is disabled or
        credentials are unavailable.
    """
    if not settings.feishu_enabled:
        logger.info("feishu_gateway_disabled")
        return False

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        logger.warning("feishu_credentials_not_configured")
        return False

    client = get_feishu_client()

    try:
        await client.get_access_token()
        logger.info("feishu_credentials_verified")
    except Exception as e:
        logger.error("feishu_auth_failed", error=str(e))
        return False

    event_handler = EventHandler(client, agent)
    bot_handler = BotHandler(client, agent)
    card_handler = CardHandler(client, agent, pm_client=pm_client)

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

    init_handlers(event_handler, bot_handler, card_handler, message_recorder)

    logger.info("feishu_gateway_initialized")
    return True


__all__ = [
    "BotHandler",
    "CardHandler",
    "EventHandler",
    "FeishuClient",
    "MessageRecorder",
    "SessionManager",
    "feishu_client",
    "get_feishu_client",
    "get_session_manager",
    "init_feishu_gateway",
    "init_handlers",
    "router",
]
