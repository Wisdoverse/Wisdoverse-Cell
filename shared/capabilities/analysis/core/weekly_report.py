"""Weekly report generator from the Analysis projection and Feishu task data."""
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

logger = get_logger("analysis_module.weekly_report")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")
_COMPLETED_STATUSES = {"closed", "done", "resolved", "completed"}


class WeeklyReportGenerator:
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
        feishu_tasks = await self._fetch_feishu_tasks()
        op_tasks = await self._fetch_op_tasks()
        if not feishu_tasks and not op_tasks:
            report = GeneratedAnalysisReport.generate(
                report_kind=AnalysisReportKind.WEEKLY,
                content="暂无任务数据",
                summary="无数据",
                stats=None,
            )
            self._drain_report_events(report)
            return report.to_response(include_stats=False)

        stats = self._compute_stats(feishu_tasks, op_tasks)
        content = self._format_report(feishu_tasks, op_tasks, stats=stats)
        report = GeneratedAnalysisReport.generate(
            report_kind=AnalysisReportKind.WEEKLY,
            content=content,
            summary=f"共 {stats.total} 个任务",
            stats=stats,
        )
        self._drain_report_events(report)
        return report.to_response(include_stats=False)

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

    async def _fetch_feishu_tasks(self) -> list[AnalysisFeishuTaskSnapshot]:
        projections = await self._projection_port.list_subtask_progress()
        return self._feishu_task_acl.from_projection_rows(projections)

    async def _fetch_op_tasks(self) -> list[WorkPackageProjection]:
        if not self._config.decompose_project_ids:
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

    def _format_report(
        self,
        feishu_tasks: list[AnalysisFeishuTaskSnapshot],
        op_tasks: list[WorkPackageProjection],
        *,
        stats: AnalysisReportStats | None = None,
    ) -> str:
        now = datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")
        stats = stats or self._compute_stats(feishu_tasks, op_tasks)

        # Feishu task categories
        fs_completed = [task for task in feishu_tasks if task.is_completed]
        fs_blocked = [task for task in feishu_tasks if task.is_blocked]

        # OpenProject task categories — typed projection access
        op_completed = [
            wp for wp in op_tasks if wp.status_name.lower() in _COMPLETED_STATUSES
        ]

        lines = [
            f"📋 每周项目周报 ({now})\n",
            f"🔹 飞书任务：完成 {stats.feishu.completed} 个，"
            f"进行中 {stats.feishu.in_progress} 个，"
            f"阻塞 {stats.feishu.blocked} 个",
            f"🔹 OP 任务：完成 {stats.op.completed} 个，"
            f"进行中 {stats.op.in_progress} 个\n",
        ]

        if fs_completed:
            lines.append("✅ 飞书本周完成：")
            for task in fs_completed[:10]:
                lines.append(f"  • {task.title}")

        if op_completed:
            lines.append("\n✅ OP 本周完成：")
            for wp in op_completed[:10]:
                lines.append(f"  • {wp.subject or '未命名'}")

        if fs_blocked:
            lines.append("\n🚫 阻塞中（飞书）：")
            for task in fs_blocked:
                lines.append(f"  • {task.title} — {task.blocked_reason_or_default}")

        return "\n".join(lines)

    def _compute_stats(
        self,
        feishu_tasks: list[AnalysisFeishuTaskSnapshot],
        op_tasks: list[WorkPackageProjection],
    ) -> AnalysisReportStats:
        return AnalysisReportStats.from_sources(
            feishu_tasks=feishu_tasks,
            op_tasks=op_tasks,
        )

    def _drain_report_events(self, report: GeneratedAnalysisReport) -> None:
        for event in report.pull_events():
            logger.debug(
                "analysis_report_domain_event_raised",
                domain_event=event.event_name,
                report_kind=event.report_kind.value,
                total_tasks=event.total_tasks,
            )
