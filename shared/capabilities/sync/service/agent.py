"""SyncModule - scheduled support capability for external work sync."""
from typing import Optional

from shared.config import settings as app_settings
from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.application_facade import SyncApplicationFacade
from ..core.engine import SyncEngine
from ..core.health_ports import SyncHealthStore
from ..core.sync_ports import SyncEventOutboxStore
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemySyncHealthStore
from ..db.sync_stores import (
    SqlAlchemyFeishuBitableSyncStore,
    SqlAlchemyOpenProjectSyncStore,
    SqlAlchemySyncEventOutboxStore,
    SqlAlchemySyncLockStore,
)

try:
    from ..app.metrics import SYNC_DURATION, SYNC_RECORDS_PROCESSED, SYNC_RUNS
    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("sync_module.service")


class SyncModule(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        outbox_store: SyncEventOutboxStore | None = None,
        health_store: SyncHealthStore | None = None,
    ):
        super().__init__(
            agent_id="sync-module",
            agent_name="Sync Capability",
            subscribed_events=[EventTypes.SYNC_TRIGGER],
            published_events=[
                EventTypes.SYNC_STARTED,
                EventTypes.SYNC_COMPLETED,
                EventTypes.SYNC_FAILED,
                EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store or SqlAlchemySyncEventOutboxStore(
            self._db_manager
        )
        self._health_store = health_store or SqlAlchemySyncHealthStore(
            self._db_manager
        )
        self._sync_engine: SyncEngine | None = None
        self._decompose_project_ids: set[int] = set()
        if app_settings.decompose_project_ids.strip():
            self._decompose_project_ids = {
                int(x.strip()) for x in app_settings.decompose_project_ids.split(",") if x.strip()
            }
        self._application = SyncApplicationFacade(
            agent_id=self.agent_id,
            standard_request_handler=self.handle_standard_request,
            sync_engine_provider=lambda: self._sync_engine,
            health_store=self._health_store,
            outbox_store_provider=lambda: self._outbox_store,
            event_factory=self,
            event_publisher=self._event_publisher,
            metrics=self,
        )

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        self._sync_engine = SyncEngine(
            openproject_store=SqlAlchemyOpenProjectSyncStore(self._db_manager),
            lock_store=SqlAlchemySyncLockStore(self._db_manager),
            feishu_bitable_store=SqlAlchemyFeishuBitableSyncStore(self._db_manager),
            op_client=get_op_client(),
            bitable=bitable_service,
            event_publisher=self._event_publisher,
            decompose_filter=self._should_decompose,
            member_table_app_token=app_settings.feishu_pm_app_token,
            member_table_id=app_settings.feishu_pm_member_table_id,
        )

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        if self._sync_engine:
            op_client = getattr(self._sync_engine, "_op", None)
            if op_client and hasattr(op_client, "close"):
                await op_client.close()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._application.health_check()

    def _should_decompose(self, project_id: int) -> bool:
        return project_id in self._decompose_project_ids

    async def trigger_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run both sync boundaries and publish compatibility sync events."""
        return await self._application.trigger_sync(
            triggered_by=triggered_by,
            trace_id=trace_id,
        )

    async def trigger_openproject_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run the OpenProject-to-Bitable projection sync only."""
        return await self._application.trigger_openproject_sync(
            triggered_by=triggered_by,
            trace_id=trace_id,
        )

    async def trigger_feishu_bitable_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run the Feishu Bitable-to-OpenProject progress sync only."""
        return await self._application.trigger_feishu_bitable_sync(
            triggered_by=triggered_by,
            trace_id=trace_id,
        )

    async def _run_sync_scope(
        self,
        scope: str,
        triggered_by: str,
        trace_id: str | None,
        runner,
    ) -> dict:
        return await self._application.run_sync_scope(
            scope=scope,
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=runner,
        )

    async def publish_sync_event_via_outbox(self, event: Event) -> None:
        await self._application.publish_sync_event_via_outbox(event)

    def record_sync_success(
        self,
        *,
        triggered_by: str,
        scope: str,
        synced_count: int,
        duration_seconds: float,
    ) -> None:
        if not _metrics_available:
            return
        SYNC_RUNS.labels(triggered_by=triggered_by, status="success").inc()
        SYNC_DURATION.observe(duration_seconds)
        SYNC_RECORDS_PROCESSED.labels(direction=scope).inc(synced_count)

    def record_sync_failure(self, *, triggered_by: str) -> None:
        if not _metrics_available:
            return
        SYNC_RUNS.labels(triggered_by=triggered_by, status="failed").inc()

    async def publish_pending_sync_events(self, limit: int = 100) -> dict[str, int]:
        """
        Retry pending Sync outbox events.

        Runtime plugins and future workers can reuse this without depending on
        persistence details.
        """
        return await self._application.publish_pending_sync_events(limit=limit)

    async def _publish_sync_event_via_outbox(self, event: Event) -> None:
        """Stage a Sync event in its outbox, then publish after local commit."""
        await self._application.publish_sync_event_via_outbox(event)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Sync event before EventBus delivery."""
        return await self._application.publish_event_via_outbox(event)


# Global capability singleton.
agent = SyncModule()


def get_agent() -> SyncModule:
    """Return the current capability instance and support test replacement."""
    return agent
