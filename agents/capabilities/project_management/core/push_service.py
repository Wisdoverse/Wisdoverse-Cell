"""推送服务 - 向飞书群发送消息"""

import json

from shared.config import settings
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

logger = get_logger("pjm_agent.push")


class PushService:
    async def send_to_chat(self, chat_id: str, content: str, msg_type: str = "text") -> bool:
        try:
            client = get_feishu_client()
            await client.send_message(
                receive_id=chat_id,
                receive_id_type="chat_id",
                msg_type=msg_type,
                content=content,
            )
            logger.info("push_sent", chat_id=chat_id)
            return True
        except Exception as e:
            logger.error("push_failed", chat_id=chat_id, error=str(e))
            return False

    async def push_risks(self, risks: list[dict]) -> bool:
        if not risks or not settings.feishu_report_chat_id:
            return False
        lines = ["🔍 风险检测通知\n"]
        for r in risks:
            level = r.get("risk_level", "unknown")
            icon = "🔴" if level == "high" else "🟡" if level == "medium" else "🟢"
            lines.append(f"{icon} [{level}] {r.get('message', '未知风险')}")
        text = "\n".join(lines)
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(settings.feishu_report_chat_id, content)

    async def push_alerts(self, alerts: list[dict]) -> bool:
        if not alerts:
            return False
        if not settings.feishu_report_chat_id:
            logger.warning("push_alerts_no_chat_id", alert_count=len(alerts))
            return False
        lines = ["⚠️ PM 预警通知\n"]
        for a in alerts:
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            lines.append(f"{icon} [{a['type']}] {a['task']}: {a['message']}")
        text = "\n".join(lines)
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(settings.feishu_report_chat_id, content)

    async def send_decompose_failure(self, wp_id: int, subject: str, error_message: str) -> bool:
        """Notify Feishu chat that a decomposition failed."""
        chat_id = (
            getattr(settings, "decompose_notify_open_id", "") or settings.feishu_report_chat_id
        )
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
        chat_id = (
            getattr(settings, "decompose_notify_open_id", "") or settings.feishu_report_chat_id
        )
        if not chat_id:
            return False
        text = (
            f"⏰ 拆解审批提醒\n\n"
            f"工作包: #{wp_id} {subject}\n"
            f"此拆解已等待审批超过 24 小时，请尽快处理。"
        )
        content = json.dumps({"text": text}, ensure_ascii=False)
        return await self.send_to_chat(chat_id, content)
