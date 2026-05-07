"""Weekly report generator from OpenProject and Feishu task data."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.core import BitableTablePort, FeishuMessengerPort, OpenProjectWorkPackagePort
from shared.utils.logger import get_logger

from .config import AnalysisCoreConfig

logger = get_logger("analysis_module.weekly_report")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")


class WeeklyReportGenerator:
    def __init__(
        self,
        bitable: BitableTablePort,
        messenger: FeishuMessengerPort,
        op_client: OpenProjectWorkPackagePort,
        config: AnalysisCoreConfig | None = None,
    ):
        self._bitable = bitable
        self._messenger = messenger
        self._op = op_client
        self._config = config or AnalysisCoreConfig()

    async def generate(self) -> dict:
        feishu_tasks = await self._fetch_feishu_tasks()
        op_tasks = await self._fetch_op_tasks()
        if not feishu_tasks and not op_tasks:
            return {"content": "暂无任务数据", "summary": "无数据"}

        content = self._format_report(feishu_tasks, op_tasks)
        return {"content": content, "summary": f"共 {len(feishu_tasks) + len(op_tasks)} 个任务"}

    async def push_to_chat(self, content: str) -> bool:
        chat_id = self._config.feishu_report_chat_id
        if not chat_id:
            return False
        try:
            msg = json.dumps({"text": content}, ensure_ascii=False)
            await self._messenger.send_message(
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
        app_token = self._config.feishu_pm_app_token
        table_id = self._config.feishu_pm_task_table_id
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
        if not self._config.decompose_project_ids:
            return []
        wps = []
        for pid in self._config.decompose_project_ids:
            try:
                items = await self._op.get_work_packages(project_id=int(pid))
                wps.extend(items)
            except Exception as e:
                logger.error("fetch_op_tasks_failed", project_id=pid, error=str(e))
        return wps

    def _format_report(self, feishu_tasks: list[dict], op_tasks: list[dict]) -> str:
        now = datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")

        # Feishu task categories
        fs_completed = [t for t in feishu_tasks if "完成" in t.get("状态", "")]
        fs_in_progress = [t for t in feishu_tasks if "进行中" in t.get("状态", "")]
        fs_blocked = [t for t in feishu_tasks if "阻塞" in t.get("状态", "")]

        # OpenProject task categories
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
