"""周报生成器 - 从 OP + 飞书生成周报"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.config import settings
from shared.integrations.feishu.bitable import BitableService
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import OpenProjectClient, get_op_client
from shared.utils.logger import get_logger

logger = get_logger("analysis_agent.weekly_report")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")


class WeeklyReportGenerator:
    def __init__(self, bitable: BitableService, op_client: OpenProjectClient | None = None):
        self._bitable = bitable
        self._op = op_client or get_op_client()

    async def generate(self) -> dict:
        feishu_tasks = await self._fetch_feishu_tasks()
        op_tasks = await self._fetch_op_tasks()
        if not feishu_tasks and not op_tasks:
            return {"content": "暂无任务数据", "summary": "无数据"}

        content = self._format_report(feishu_tasks, op_tasks)
        return {"content": content, "summary": f"共 {len(feishu_tasks) + len(op_tasks)} 个任务"}

    async def push_to_chat(self, content: str) -> bool:
        chat_id = settings.feishu_report_chat_id
        if not chat_id:
            return False
        try:
            client = get_feishu_client()
            msg = json.dumps({"text": content}, ensure_ascii=False)
            await client.send_message(
                receive_id=chat_id,
                receive_id_type="chat_id",
                msg_type="text",
                content=msg,
            )
            logger.info("weekly_report_pushed")
            return True
        except Exception as e:
            logger.error("weekly_report_push_failed", error=str(e))
            return False

    async def _fetch_feishu_tasks(self) -> list[dict]:
        app_token = settings.feishu_pm_app_token
        table_id = settings.feishu_pm_task_table_id
        if not app_token or not table_id:
            logger.warning(
                "fetch_feishu_tasks_missing_config",
                has_app_token=bool(app_token),
                has_table_id=bool(table_id),
            )
            return []
        records = await self._bitable.list_all_records(app_token=app_token, table_id=table_id)
        return [r.get("fields", {}) for r in records]

    async def _fetch_op_tasks(self) -> list[dict]:
        if not settings.decompose_project_ids.strip():
            return []
        project_ids = [p.strip() for p in settings.decompose_project_ids.split(",") if p.strip()]
        wps = []
        for pid in project_ids:
            try:
                items = await self._op.get_work_packages(project_id=int(pid))
                wps.extend(items)
            except Exception as e:
                logger.error("fetch_op_tasks_failed", project_id=pid, error=str(e))
        return wps

    def _format_report(self, feishu_tasks: list[dict], op_tasks: list[dict]) -> str:
        now = datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")

        # 飞书任务分类
        fs_completed = [t for t in feishu_tasks if "完成" in t.get("状态", "")]
        fs_in_progress = [t for t in feishu_tasks if "进行中" in t.get("状态", "")]
        fs_blocked = [t for t in feishu_tasks if "阻塞" in t.get("状态", "")]

        # OP 任务分类
        op_completed = [
            t for t in op_tasks
            if t.get("_links", {}).get("status", {})
            .get("title", "").lower() in {"closed", "done", "resolved"}
        ]
        op_in_progress = [
            t for t in op_tasks
            if "progress" in t.get("_links", {})
            .get("status", {}).get("title", "").lower()
        ]

        lines = [
            f"📋 每周项目周报 ({now})\n",
            f"🔹 飞书任务：完成 {len(fs_completed)} 个，"
            f"进行中 {len(fs_in_progress)} 个，"
            f"阻塞 {len(fs_blocked)} 个",
            f"🔹 OP 任务：完成 {len(op_completed)} 个，进行中 {len(op_in_progress)} 个\n",
        ]

        if fs_completed:
            lines.append("✅ 飞书本周完成：")
            for t in fs_completed[:10]:
                lines.append(f"  • {t.get('任务(动宾短语)', '未命名')}")

        if op_completed:
            lines.append("\n✅ OP 本周完成：")
            for t in op_completed[:10]:
                lines.append(f"  • {t.get('subject', '未命名')}")

        if fs_blocked:
            lines.append("\n🚫 阻塞中（飞书）：")
            for t in fs_blocked:
                name = t.get("任务(动宾短语)", "未命名")
                reason = t.get("阻塞原因", "未说明")
                lines.append(f"  • {name} — {reason}")

        return "\n".join(lines)
