"""Daily report generator from the Analysis projection and Feishu task data."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.core import BitableTablePort, FeishuMessengerPort
from shared.utils.logger import get_logger

from .config import AnalysisCoreConfig
from .domain.projection import WorkPackageProjection, WorkPackageProjectionPort

logger = get_logger("analysis_module.daily_report")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")
_COMPLETED_STATUSES = {"closed", "done", "resolved", "completed"}


class DailyReportGenerator:
    def __init__(
        self,
        bitable: BitableTablePort,
        messenger: FeishuMessengerPort,
        projection_port: WorkPackageProjectionPort,
        config: AnalysisCoreConfig | None = None,
    ):
        self._bitable = bitable
        self._messenger = messenger
        self._projection_port = projection_port
        self._config = config or AnalysisCoreConfig()

    async def generate(self) -> dict:
        """Generate daily report content with summary and stats."""
        feishu_tasks = await self._fetch_feishu_tasks()
        op_tasks = await self._fetch_op_tasks()

        if not feishu_tasks and not op_tasks:
            return {"content": "暂无任务数据", "summary": "无数据", "stats": {}}

        stats = self._compute_stats(feishu_tasks, op_tasks)
        content = self._format_report(stats, feishu_tasks, op_tasks)
        return {"content": content, "summary": f"共 {stats['total']} 个任务", "stats": stats}

    async def push_to_chat(self, content: str) -> bool:
        """Push daily report content to the configured Feishu chat."""
        chat_id = self._config.feishu_report_chat_id
        if not chat_id:
            logger.warning("daily_report_no_chat_id")
            return False
        try:
            msg = json.dumps({"text": content}, ensure_ascii=False)
            await self._messenger.send_message(
                receive_id=chat_id,
                receive_id_type="chat_id",
                msg_type="text",
                content=msg,
            )
            logger.info("daily_report_pushed")
            return True
        except Exception as e:
            logger.error("daily_report_push_failed", error=str(e))
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

    async def _fetch_op_tasks(self) -> list[WorkPackageProjection]:
        if not self._config.decompose_project_ids:
            logger.warning("fetch_op_tasks_no_project_ids")
            return []
        wps: list[WorkPackageProjection] = []
        for pid in self._config.decompose_project_ids:
            try:
                items = await self._projection_port.list_work_packages(
                    project_id=int(pid)
                )
                wps.extend(items)
            except Exception as e:
                logger.error("fetch_op_tasks_failed", project_id=pid, error=str(e))
        return wps

    def _compute_stats(
        self,
        feishu_tasks: list[dict],
        op_tasks: list[WorkPackageProjection],
    ) -> dict:
        # Feishu task statistics
        fs_total = len(feishu_tasks)
        fs_completed = sum(1 for t in feishu_tasks if "完成" in t.get("状态", ""))
        fs_in_progress = sum(1 for t in feishu_tasks if "进行中" in t.get("状态", ""))
        fs_blocked = sum(1 for t in feishu_tasks if "阻塞" in t.get("状态", ""))

        # OpenProject task statistics — typed projection access
        op_total = len(op_tasks)
        op_completed = sum(
            1 for wp in op_tasks if wp.status_name.lower() in _COMPLETED_STATUSES
        )
        op_in_progress = sum(
            1 for wp in op_tasks if "progress" in wp.status_name.lower()
        )

        return {
            "total": fs_total + op_total,
            "feishu": {
                "total": fs_total,
                "completed": fs_completed,
                "in_progress": fs_in_progress,
                "blocked": fs_blocked,
            },
            "op": {"total": op_total, "completed": op_completed, "in_progress": op_in_progress},
        }

    def _format_report(
        self,
        stats: dict,
        feishu_tasks: list[dict],
        op_tasks: list[WorkPackageProjection],
    ) -> str:
        now = datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")
        fs = stats["feishu"]
        op = stats["op"]

        lines = [
            f"📊 每日项目日报 ({now})\n",
            f"📈 任务总览：共 {stats['total']} 个\n",
            f"🔹 飞书任务：{fs['total']} 个",
            f"  ✅ 已完成: {fs['completed']}",
            f"  🔄 进行中: {fs['in_progress']}",
            f"  🚫 阻塞: {fs['blocked']}\n",
            f"🔹 OP 任务：{op['total']} 个",
            f"  ✅ 已完成: {op['completed']}",
            f"  🔄 进行中: {op['in_progress']}",
        ]

        # Blocked task details
        blocked_tasks = [t for t in feishu_tasks if "阻塞" in t.get("状态", "")]
        if blocked_tasks:
            lines.append("\n🚨 阻塞任务（飞书）：")
            for t in blocked_tasks:
                name = t.get("任务(动宾短语)", "未命名")
                reason = t.get("阻塞原因", "未说明")
                lines.append(f"  • {name} — {reason}")

        return "\n".join(lines)
