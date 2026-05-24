"""Milestone risk checker."""
import json

from shared.core import FeishuMessengerPort
from shared.utils.logger import get_logger

from .config import AnalysisCoreConfig
from .domain.assessment import AnalysisMilestoneTaskSnapshot, MilestoneRiskSignal
from .domain.projection import WorkPackageProjectionPort

logger = get_logger("analysis_module.milestone")


class MilestoneChecker:
    def __init__(
        self,
        messenger: FeishuMessengerPort,
        projection_port: WorkPackageProjectionPort,
        config: AnalysisCoreConfig | None = None,
    ):
        self._messenger = messenger
        self._projection_port = projection_port
        self._config = config or AnalysisCoreConfig()

    async def check(self) -> list[dict]:
        """Check milestone-linked subtask risks."""
        return [risk.to_event_payload() for risk in await self.check_signals()]

    async def check_signals(self) -> list[MilestoneRiskSignal]:
        """Check milestone-linked subtask risks as domain value objects."""
        tasks = await self._fetch_tasks()
        risks: list[MilestoneRiskSignal] = []

        # Group by Feature ID
        by_feature: dict[str, list[AnalysisMilestoneTaskSnapshot]] = {}
        for task in tasks:
            if task.has_feature:
                by_feature.setdefault(task.feature_id, []).append(task)

        for fid, subtasks in by_feature.items():
            blocked = [task for task in subtasks if task.is_blocked]
            total = len(subtasks)
            completed = sum(1 for task in subtasks if task.is_completed)

            if blocked:
                risks.append(
                    MilestoneRiskSignal.blocked_subtasks(
                        feature_id=fid,
                        total=total,
                        blocked_tasks=[task.title for task in blocked],
                    )
                )

            if total > 0 and completed / total < 0.3:
                # Feature progress below 30%
                risks.append(
                    MilestoneRiskSignal.low_progress(
                        feature_id=fid,
                        completed=completed,
                        total=total,
                    )
                )

        return risks

    async def push_risks(self, risks: list[dict]) -> bool:
        if not risks or not self._config.feishu_report_chat_id:
            return False
        try:
            signals = [
                MilestoneRiskSignal.from_event_payload(risk) for risk in risks
            ]
            lines = ["🚩 里程碑风险预警\n"]
            for signal in signals:
                lines.append(f"{signal.notification_icon} {signal.message}")
                for blocked_task in signal.blocked_tasks:
                    lines.append(f"    ↳ {blocked_task}")

            content = json.dumps({"text": "\n".join(lines)}, ensure_ascii=False)
            await self._messenger.send_message(
                receive_id=self._config.feishu_report_chat_id,
                receive_id_type="chat_id", msg_type="text", content=content,
            )
            logger.info("milestone_risks_pushed", count=len(risks))
            return True
        except Exception as e:
            logger.error("milestone_push_failed", error=str(e))
            return False

    async def _fetch_tasks(self) -> list[AnalysisMilestoneTaskSnapshot]:
        projections = await self._projection_port.list_subtask_progress()
        return [
            AnalysisMilestoneTaskSnapshot.from_projection(projection)
            for projection in projections
        ]
