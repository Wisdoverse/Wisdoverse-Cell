"""
PMAgent - alert scheduling and task decomposition agent.

Subscribes to sync.completed, analysis.risk-detected, chat.pm-query, and
sync.task-needs-decompose. Handles alert checks, risk notifications, PM query
responses, and automated task decomposition.
"""

from typing import Optional

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..adapters.feishu_card_acl import PJMFeishuCardACL
from ..adapters.feishu_cards import FeishuPJMCardRenderer
from ..core.alert_ports import PJMAlertLogStore
from ..core.alert_service import AlertService
from ..core.application_facade import PJMApplicationFacade
from ..core.config_service import PMConfigService
from ..core.decompose import DecomposeService
from ..core.decomposition_orchestrator import DecompositionOrchestrator
from ..core.decomposition_ports import PJMDecompositionStore
from ..core.event_use_cases import PJMMetricsPort
from ..core.health_ports import PJMHealthStore
from ..core.op_writer import OPWriterService
from ..core.push_service import PushService
from ..core.report_service import ReportService
from ..db.alert_log_store import SqlAlchemyPJMAlertLogStore
from ..db.database import DatabaseManager, db_manager
from ..db.decomposition_store import SqlAlchemyPJMDecompositionStore
from ..db.health_store import SqlAlchemyPJMHealthStore
from ..db.outbox_store import SqlAlchemyPJMEventOutboxStore
from .config_factory import build_pjm_core_config

try:
    from ..app.metrics import ALERTS_TRIGGERED

    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("pjm_agent.service")


class _PJMMetrics(PJMMetricsPort):
    def record_alert_triggered(self, *, alert_type: str, severity: str) -> None:
        if _metrics_available:
            ALERTS_TRIGGERED.labels(alert_type=alert_type, severity=severity).inc()


class PMAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        decomposition_store: PJMDecompositionStore | None = None,
        alert_log_store: PJMAlertLogStore | None = None,
        health_store: PJMHealthStore | None = None,
    ):
        super().__init__(
            agent_id="pjm-agent",
            agent_name="PJM Agent",
            subscribed_events=[
                EventTypes.SYNC_COMPLETED,
                EventTypes.ANALYSIS_RISK_DETECTED,
                EventTypes.CHAT_PM_QUERY,
                EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
                EventTypes.COORDINATOR_DISPATCH,
            ],
            published_events=[
                EventTypes.PM_ALERT_TRIGGERED,
                EventTypes.CHAT_PM_RESPONSE,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_DECOMPOSITION_FAILED,
                EventTypes.PM_APPROVAL_TIMEOUT,
                EventTypes.PM_TASKS_READY_FOR_DEV,
                EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._decomposition_store = decomposition_store or SqlAlchemyPJMDecompositionStore(
            self._db_manager
        )
        self._alert_log_store = alert_log_store or SqlAlchemyPJMAlertLogStore(self._db_manager)
        self._health_store = health_store or SqlAlchemyPJMHealthStore(self._db_manager)
        self._config: PMConfigService | None = None
        self._alert: AlertService | None = None
        self._push: PushService | None = None
        self._decompose: DecomposeService | None = None
        self._op_writer: OPWriterService | None = None
        self._report: ReportService | None = None
        self._decomposition_orchestrator: DecompositionOrchestrator | None = None
        self._core_config = build_pjm_core_config()
        self._application = PJMApplicationFacade(
            standard_request_handler=self.handle_standard_request,
            config_provider=lambda: self._config,
            alert_provider=lambda: self._alert,
            push_provider=lambda: self._push,
            report_provider=lambda: self._report,
            decomposition_provider=lambda: self._decomposition_orchestrator,
            decomposition_store_provider=lambda: self._decomposition_store,
            alert_log_store=self._alert_log_store,
            health_store=self._health_store,
            event_factory=self,
            metrics=_PJMMetrics(),
        )

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        self._config = PMConfigService(bitable_service, config=self._core_config)
        self._alert = AlertService(
            bitable_service,
            self._config,
            core_config=self._core_config,
        )
        op_client = get_op_client()
        feishu_client = get_feishu_client()
        card_renderer = PJMFeishuCardACL(FeishuPJMCardRenderer())

        self._push = PushService(feishu_client, config=self._core_config)
        self._decompose = DecomposeService(llm_gateway, config=self._core_config)
        self._op_writer = OPWriterService(op_client)
        self._report = ReportService(
            op_client,
            bitable_service,
            card_renderer=card_renderer,
            messenger=feishu_client,
            config=self._core_config,
        )
        self._decomposition_orchestrator = DecompositionOrchestrator(
            db_manager=self._db_manager,
            op_writer=self._op_writer,
            decompose_service=self._decompose,
            push_service=self._push,
            create_event_fn=self.create_event,
            event_publisher=EventBusEventPublisher(self._event_bus),
            op_client=op_client,
            messenger=feishu_client,
            card_renderer=card_renderer,
            outbox_store=SqlAlchemyPJMEventOutboxStore(self._db_manager),
            decomposition_store=self._decomposition_store,
            config=self._core_config,
        )
        await self._config.refresh()

        # Event loop is managed by AgentRuntime.start_event_loop()
        # This ensures events go through EvolvedAgent for trace collection

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._application.health_check()

    async def publish_pending_pjm_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending PJM outbox events through the decomposition boundary."""
        return await self._application.publish_pending_pjm_events(limit=limit)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced PJM event before EventBus delivery."""
        await self._publish_pjm_event_via_outbox(event)
        return True

    async def _publish_pjm_event_via_outbox(
        self,
        event: Event,
        *,
        wp_id: int | None = None,
    ) -> None:
        """Publish a PJM notification through the durable outbox boundary."""
        await self._application.publish_event_via_outbox(event, wp_id=wp_id)

    async def check_approval_timeouts(self):
        """Scan for pending approvals older than 24h and send reminders."""
        await self._application.check_approval_timeouts()

    async def approve_decomposition(self, wp_id: int, approved_by: str) -> dict | None:
        """Delegate to DecompositionOrchestrator."""
        return await self._application.approve_decomposition(wp_id, approved_by)

    async def reject_decomposition(
        self, wp_id: int, rejected_by: str, reason: str = ""
    ) -> dict | None:
        """Delegate to DecompositionOrchestrator."""
        return await self._application.reject_decomposition(wp_id, rejected_by, reason=reason)


agent = PMAgent()


def get_agent() -> PMAgent:
    return agent
