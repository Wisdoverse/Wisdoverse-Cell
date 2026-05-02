"""Feishu notification helper for dev_agent."""
from __future__ import annotations

import json

from shared.utils.logger import get_logger

logger = get_logger("dev_agent.notifier")


class DevNotifier:
    """Sends Feishu notifications for dev_agent events.

    Connects to shared/integrations/feishu/ when feishu is enabled.
    Falls back to logging when feishu is unavailable.
    """

    def __init__(self) -> None:
        self._feishu = None
        self._chat_id: str = ""
        try:
            from shared.config import settings

            if getattr(settings, "feishu_enabled", False):
                from shared.integrations.feishu import get_feishu_client

                self._feishu = get_feishu_client()
                self._chat_id = getattr(settings, "feishu_default_chat_id", "")
            else:
                logger.info("feishu_not_configured")
        except Exception:
            logger.info("feishu_not_available", exc_info=True)

    async def notify_mr_created(
        self,
        wp_id: int,
        mr_url: str,
        risk_level: str,
        task_title: str = "",
    ) -> None:
        msg = f"[DevAgent] MR Created: WP#{wp_id} ({risk_level})\n{mr_url}"
        logger.info(
            "notify_mr_created",
            wp_id=wp_id,
            mr_url=mr_url,
            risk_level=risk_level,
        )
        await self._send(msg)

    async def notify_task_failed(
        self,
        wp_id: int,
        error: str,
        failed_node: str = "",
        runbook_url: str = "",
    ) -> None:
        msg = f"[DevAgent] Task Failed: WP#{wp_id}\nError: {error}"
        if failed_node:
            msg += f"\nFailed node: {failed_node}"
        logger.warning(
            "notify_task_failed",
            wp_id=wp_id,
            error=error,
            failed_node=failed_node,
        )
        await self._send(msg)

    async def notify_task_completed(
        self, wp_id: int, mr_url: str
    ) -> None:
        msg = f"[DevAgent] Task Completed: WP#{wp_id}\nMR: {mr_url}"
        logger.info(
            "notify_task_completed", wp_id=wp_id, mr_url=mr_url
        )
        await self._send(msg)

    async def _send(self, text: str) -> None:
        if not self._feishu or not self._chat_id:
            return
        try:
            content = json.dumps({"text": text})
            await self._feishu.send_message(
                receive_id=self._chat_id,
                receive_id_type="chat_id",
                msg_type="text",
                content=content,
            )
        except Exception as e:
            logger.error("feishu_send_failed", error=str(e), exc_info=True)
