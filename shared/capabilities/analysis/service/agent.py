"""Analysis capability module for reports, milestone checks, and quality review."""
from typing import Optional

from shared.config import settings as app_settings
from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.config import AnalysisCoreConfig
from ..core.daily_report import DailyReportGenerator
from ..core.event_use_cases import AnalysisEventUseCase
from ..core.health_ports import AnalysisHealthStore
from ..core.health_use_cases import AnalysisHealthUseCase
from ..core.milestone_checker import MilestoneChecker
from ..core.outbox_delivery_use_cases import AnalysisOutboxDeliveryUseCase
from ..core.outbox_ports import AnalysisEventOutboxStore
from ..core.quality_evaluator import QualityEvaluator
from ..core.request_use_cases import AnalysisRequestUseCase
from ..core.weekly_report import WeeklyReportGenerator
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyAnalysisHealthStore
from ..db.outbox_store import SqlAlchemyAnalysisEventOutboxStore

try:
    from ..app.metrics import REPORTS_GENERATED, RISKS_DETECTED
    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("analysis_module.service")


class _AnalysisMetrics:
    def record_report(self, report_type: str) -> None:
        if _metrics_available:
            REPORTS_GENERATED.labels(report_type=report_type).inc()

    def record_risk(self, risk_level: str) -> None:
        if _metrics_available:
            RISKS_DETECTED.labels(risk_level=risk_level).inc()


class AnalysisModule(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        outbox_store: Optional[AnalysisEventOutboxStore] = None,
        health_store: AnalysisHealthStore | None = None,
    ):
        super().__init__(
            agent_id="analysis-module",
            agent_name="Analysis Capability",
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
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store or SqlAlchemyAnalysisEventOutboxStore(
            self._db_manager
        )
        self._health_store = health_store or SqlAlchemyAnalysisHealthStore(
            self._db_manager
        )
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

        messenger = get_feishu_client()
        op_client = get_op_client()
        core_config = AnalysisCoreConfig.from_values(
            feishu_report_chat_id=app_settings.feishu_report_chat_id,
            feishu_pm_app_token=app_settings.feishu_pm_app_token,
            feishu_pm_task_table_id=app_settings.feishu_pm_task_table_id,
            decompose_project_ids=app_settings.decompose_project_ids,
        )
        self._daily = DailyReportGenerator(
            bitable=bitable_service,
            messenger=messenger,
            op_client=op_client,
            config=core_config,
        )
        self._weekly = WeeklyReportGenerator(
            bitable=bitable_service,
            messenger=messenger,
            op_client=op_client,
            config=core_config,
        )
        self._milestone = MilestoneChecker(
            bitable=bitable_service,
            messenger=messenger,
            config=core_config,
        )
        self._quality = QualityEvaluator(
            bitable_service,
            llm_gateway=llm_gateway,
            config=core_config,
        )

        # Event loop is managed by AgentRuntime.start_event_loop()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> AnalysisEventUseCase:
        return AnalysisEventUseCase(
            daily=self._daily,
            weekly=self._weekly,
            milestone=self._milestone,
            quality=self._quality,
            event_factory=self,
            metrics=_AnalysisMetrics(),
        )

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> AnalysisRequestUseCase:
        return AnalysisRequestUseCase(
            daily=self._daily,
            weekly=self._weekly,
            milestone=self._milestone,
        )

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._health_use_case().check()

    def _health_use_case(self) -> AnalysisHealthUseCase:
        return AnalysisHealthUseCase(
            health_store=self._health_store,
            event_bus=self._event_bus,
        )

    async def publish_pending_analysis_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending Analysis outbox events."""
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Analysis event before EventBus delivery."""
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> AnalysisOutboxDeliveryUseCase:
        return AnalysisOutboxDeliveryUseCase(
            outbox_store=self._outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from an Analysis outbox row."""
        return self._outbox_delivery_use_case().event_from_outbox(row)

    async def _publish_staged_analysis_event(self, event: Event) -> bool:
        """Publish one event already persisted in the Analysis outbox."""
        return await self._outbox_delivery_use_case().publish_staged_event(event)

    async def _mark_analysis_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published Analysis outbox event."""
        await self._outbox_delivery_use_case().mark_event_published(event)

    async def _mark_analysis_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an Analysis outbox publish attempt."""
        await self._outbox_delivery_use_case().mark_event_failed(event, error)

agent = AnalysisModule()


def get_agent() -> AnalysisModule:
    return agent
