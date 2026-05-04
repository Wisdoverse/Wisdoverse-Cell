"""Feishu webhook adapter."""
from __future__ import annotations

from typing import Any

import httpx

from shared.utils.logger import get_logger

logger = get_logger("integrations.feishu.webhook")


class FeishuWebhookClient:
    """HTTP adapter for Feishu incoming webhooks."""

    async def send_interactive_card(
        self,
        *,
        webhook_url: str,
        card: dict[str, Any],
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(webhook_url, json=card)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.error(
                "feishu_webhook_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False
