"""Push PM notifications to Feishu chats."""

import json

from shared.core import FeishuMessengerPort
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .config import PJMCoreConfig

logger = get_logger("pjm_agent.push")


class PushService:
    def __init__(
        self,
        messenger: FeishuMessengerPort,
        config: PJMCoreConfig | None = None,
    ):
        self._messenger = messenger
        self._config = config or PJMCoreConfig()

    async def send_to_chat(self, chat_id: str, content: str, msg_type: str = "text") -> bool:
        try:
            await self._messenger.send_message(
                receive_id=chat_id,
                receive_id_type="chat_id",
                msg_type=msg_type,
                content=content,
            )
            logger.info("push_sent", chat_hash=hash_identifier(chat_id))
            return True
        except Exception as e:
            logger.error("push_failed", chat_hash=hash_identifier(chat_id), error=str(e))
            return False

    async def push_risks(self, risks: list[dict]) -> bool:
        chat_id = self._config.feishu_report_chat_id
        if not risks or not chat_id:
            return False
        lines = ["🔍 风险检测通知\n"]
        for r in risks:
            level = r.get("risk_level", "unknown")
            icon = "🔴" if level == "high" else "🟡" if level == "medium" else "🟢"
            lines.append(f"{icon} [{level}] {r.get('message', '未知风险')}")
        text = "\n".join(lines)
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(chat_id, content)

    async def push_alerts(self, alerts: list[dict]) -> bool:
        if not alerts:
            return False
        chat_id = self._config.feishu_report_chat_id
        if not chat_id:
            logger.warning("push_alerts_no_chat_id", alert_count=len(alerts))
            return False
        lines = ["⚠️ PM 预警通知\n"]
        for a in alerts:
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            lines.append(f"{icon} [{a['type']}] {a['task']}: {a['message']}")
        text = "\n".join(lines)
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(chat_id, content)

    async def send_decompose_failure(self, wp_id: int, subject: str, error_message: str) -> bool:
        """Notify Feishu chat that a decomposition failed."""
        chat_id = self._config.decompose_notification_chat_id
        if not chat_id:
            return False
        text = (
            f"❌ 任务拆解失败\n\n"
            f"工作包: #{wp_id} {subject}\n"
            f"原因: {error_message}\n\n"
            f"可使用 retry_decompose 重试"
        )
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(chat_id, content)

    async def send_stale_approval_reminder(self, wp_id: int, subject: str) -> bool:
        """Send a reminder for a decomposition pending approval > 24 hours."""
        chat_id = self._config.decompose_notification_chat_id
        if not chat_id:
            return False
        text = (
            f"⏰ 拆解审批提醒\n\n"
            f"工作包: #{wp_id} {subject}\n"
            f"此拆解已等待审批超过 24 小时，请尽快处理。"
        )
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(chat_id, content)
