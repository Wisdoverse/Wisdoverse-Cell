"""Service-layer wiring for dev_agent notification adapters."""
from __future__ import annotations

from shared.config import settings
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

from ..core.notifier import DevNotifier

logger = get_logger("dev_agent.notifier_factory")


def build_dev_notifier() -> DevNotifier:
    """Build the notifier with concrete platform adapters at the service edge."""
    try:
        if not getattr(settings, "feishu_enabled", False):
            logger.info("feishu_not_configured")
            return DevNotifier()

        chat_id = getattr(settings, "feishu_default_chat_id", "")
        return DevNotifier(messenger=get_feishu_client(), chat_id=chat_id)
    except Exception:
        logger.info("feishu_not_available", exc_info=True)
        return DevNotifier()
