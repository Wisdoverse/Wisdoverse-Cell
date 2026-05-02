"""
AnalysisAgent - 分析报告 Agent

订阅 sync.completed 事件，生成日报/周报/里程碑检查/质量评估。
"""
from datetime import UTC, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.integrations.feishu.bitable import bitable_service
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.daily_report import DailyReportGenerator
from ..core.milestone_checker import MilestoneChecker
from ..core.quality_evaluator import QualityEvaluator
from ..core.weekly_report import WeeklyReportGenerator
from ..db.database import DatabaseManager, db_manager

try:
    from ..app.metrics import REPORTS_GENERATED, RISKS_DETECTED
    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("analysis_agent.service")

_CHINA_TZ = ZoneInfo("Asia/Shanghai")


class AnalysisAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
    ):
        super().__init__(
            agent_id="analysis-agent",
            agent_name="分析Agent",
            subscribed_events=[EventTypes.SYNC_COMPLETED],
            published_events=[
                EventTypes.REPORT_DAILY_GENERATED,
                EventTypes.REPORT_WEEKLY_GENERATED,
                EventTypes.ANALYSIS_RISK_DETECTED,
                EventTypes.ANALYSIS_QUALITY_EVALUATED,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._daily: DailyReportGenerator | None = None
        self._weekly: WeeklyReportGenerator | None = None
        self._milestone: MilestoneChecker | None = None
        self._quality: QualityEvaluator | None = None

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        self._daily = DailyReportGenerator(bitable_service)
        self._weekly = WeeklyReportGenerator(bitable_service)
        self._milestone = MilestoneChecker(bitable_service)
        self._quality = QualityEvaluator(bitable_service)

        # Event loop is managed by AgentRuntime.start_event_loop()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.SYNC_COMPLETED:
            return await self._on_sync_completed(event)
        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "daily_report":
            return await self._daily.generate()
        if action == "weekly_report":
            return await self._weekly.generate()
        if action == "check_milestones":
            risks = await self._milestone.check()
            return {"risks": risks}
        return {"error": "unknown action"}

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        checks = {"database": False}
        try:
            if self._db_manager:
                from sqlalchemy import text
                async with self._db_manager.session() as session:
                    await session.execute(text("SELECT 1"))
                checks["database"] = True
        except Exception as e:
            logger.error("health_check_db_failed", error=str(e), error_type=type(e).__name__)
        checks["event_bus"] = self._event_bus is not None
        return checks

    async def _on_sync_completed(self, event: Event) -> list[Event]:
        events = []
        trace_id = event.metadata.trace_id

        # 1. 日报
        try:
            report = await self._daily.generate()
            await self._daily.push_to_chat(report["content"])
            if _metrics_available:
                REPORTS_GENERATED.labels(report_type="daily").inc()
            events.append(self.create_event(
                EventTypes.REPORT_DAILY_GENERATED,
                {"date": datetime.now(UTC).isoformat(), "summary": report["summary"]},
                trace_id=trace_id,
            ))
        except Exception as e:
            logger.error("daily_report_failed", error=str(e))

        # 2. 里程碑风险
        try:
            risks = await self._milestone.check()
            if risks:
                await self._milestone.push_risks(risks)
                if _metrics_available:
                    for r in risks:
                        RISKS_DETECTED.labels(risk_level=r.get("risk_level", "unknown")).inc()
                events.append(self.create_event(
                    EventTypes.ANALYSIS_RISK_DETECTED,
                    {"risks": risks},
                    trace_id=trace_id,
                ))
        except Exception as e:
            logger.error("milestone_check_failed", error=str(e))

        # 3. 交付物质量评估
        try:
            results = await self._quality.evaluate_all()
            if results:
                events.append(self.create_event(
                    EventTypes.ANALYSIS_QUALITY_EVALUATED,
                    {"evaluations": results},
                    trace_id=trace_id,
                ))
        except Exception as e:
            logger.error("quality_eval_failed", error=str(e))

        # 4. 周五生成周报
        if datetime.now(_CHINA_TZ).weekday() == 4:
            try:
                report = await self._weekly.generate()
                await self._weekly.push_to_chat(report["content"])
                events.append(self.create_event(
                    EventTypes.REPORT_WEEKLY_GENERATED,
                    {"summary": report["summary"]},
                    trace_id=trace_id,
                ))
            except Exception as e:
                logger.error("weekly_report_failed", error=str(e))

        return events


agent = AnalysisAgent()


def get_agent() -> AnalysisAgent:
    return agent
