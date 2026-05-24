"""Daily report generator from the Analysis projection and Feishu task data."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.core import FeishuMessengerPort
from shared.utils.logger import get_logger

from .config import AnalysisCoreConfig
from .domain.feishu_task import AnalysisFeishuTaskACL, AnalysisFeishuTaskSnapshot
from .domain.projection import WorkPackageProjection, WorkPackageProjectionPort
from .domain.report import (
    AnalysisReportKind,
    AnalysisReportStats,
    GeneratedAnalysisReport,
)

logger = get_logger("analysis_module.daily_report")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")


class DailyReportGenerator:
    def __init__(
        self,
        messenger: FeishuMessengerPort,
        projection_port: WorkPackageProjectionPort,
        config: AnalysisCoreConfig | None = None,
    ):
        self._messenger = messenger
        self._projection_port = projection_port
        self._config = config or AnalysisCoreConfig()
        self._feishu_task_acl = AnalysisFeishuTaskACL()

    async def generate(self) -> dict:
        """Generate daily report content with summary and stats."""
        feishu_tasks = await self._fetch_feishu_tasks()
        op_tasks = await self._fetch_op_tasks()

        if not feishu_tasks and not op_tasks:
            report = GeneratedAnalysisReport.generate(
                report_kind=AnalysisReportKind.DAILY,
                content="暂无任务数据",
                summary="无数据",
                stats=None,
            )
            self._drain_report_events(report)
            return report.to_response(include_stats=True)

        stats = self._compute_stats(feishu_tasks, op_tasks)
        content = self._format_report(stats, feishu_tasks, op_tasks)
        report = GeneratedAnalysisReport.generate(
            report_kind=AnalysisReportKind.DAILY,
            content=content,
            summary=f"共 {stats.total} 个任务",
            stats=stats,
        )
        self._drain_report_events(report)
        return report.to_response(include_stats=True)

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

    async def _fetch_feishu_tasks(self) -> list[AnalysisFeishuTaskSnapshot]:
        projections = await self._projection_port.list_subtask_progress()
        return self._feishu_task_acl.from_projection_rows(projections)

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
        feishu_tasks: list[AnalysisFeishuTaskSnapshot],
        op_tasks: list[WorkPackageProjection],
    ) -> AnalysisReportStats:
        return AnalysisReportStats.from_sources(
            feishu_tasks=feishu_tasks,
            op_tasks=op_tasks,
        )

    def _format_report(
        self,
        stats: AnalysisReportStats,
        feishu_tasks: list[AnalysisFeishuTaskSnapshot],
        op_tasks: list[WorkPackageProjection],
    ) -> str:
        now = datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")
        fs = stats.feishu
        op = stats.op

        lines = [
            f"📊 每日项目日报 ({now})\n",
            f"📈 任务总览：共 {stats.total} 个\n",
            f"🔹 飞书任务：{fs.total} 个",
            f"  ✅ 已完成: {fs.completed}",
            f"  🔄 进行中: {fs.in_progress}",
            f"  🚫 阻塞: {fs.blocked}\n",
            f"🔹 OP 任务：{op.total} 个",
            f"  ✅ 已完成: {op.completed}",
            f"  🔄 进行中: {op.in_progress}",
        ]

        # Blocked task details
        blocked_tasks = [task for task in feishu_tasks if task.is_blocked]
        if blocked_tasks:
            lines.append("\n🚨 阻塞任务（飞书）：")
            for task in blocked_tasks:
                lines.append(f"  • {task.title} — {task.blocked_reason_or_default}")

        return "\n".join(lines)

    def _drain_report_events(self, report: GeneratedAnalysisReport) -> None:
        for event in report.pull_events():
            logger.debug(
                "analysis_report_domain_event_raised",
                domain_event=event.event_name,
                report_kind=event.report_kind.value,
                total_tasks=event.total_tasks,
            )
