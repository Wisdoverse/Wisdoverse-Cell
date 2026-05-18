"""SyncModule - scheduled support capability for external work sync."""
from typing import Optional

from shared.config import settings as app_settings
from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..core.engine import SyncEngine
from ..core.event_use_cases import SyncEventUseCase
from ..core.health_ports import SyncHealthStore
from ..core.health_use_cases import SyncHealthUseCase
from ..core.request_use_cases import SyncRequestUseCase
from ..core.scope_execution_use_cases import SyncScopeExecutionUseCase
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
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> SyncEventUseCase:
        return SyncEventUseCase(sync_runner=self)

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> SyncRequestUseCase:
        return SyncRequestUseCase(sync_runner=self, agent_id=self.agent_id)

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._health_use_case().check()

    def _health_use_case(self) -> SyncHealthUseCase:
        return SyncHealthUseCase(health_store=self._health_store)

    def _should_decompose(self, project_id: int) -> bool:
        return project_id in self._decompose_project_ids

    async def trigger_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run both sync boundaries and publish compatibility sync events."""
        return await self._run_sync_scope(
            scope="full",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._sync_engine.full_sync(trace_id=trace_id),
        )

    async def trigger_openproject_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run the OpenProject-to-Bitable projection sync only."""
        return await self._run_sync_scope(
            scope="openproject",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._sync_engine.sync_op_to_feishu(trace_id=trace_id),
        )

    async def trigger_feishu_bitable_sync(
        self,
        triggered_by: str = "scheduler",
        trace_id: str | None = None,
    ) -> dict:
        """Run the Feishu Bitable-to-OpenProject progress sync only."""
        return await self._run_sync_scope(
            scope="feishu_bitable",
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=lambda: self._sync_engine.sync_feishu_to_op(trace_id=trace_id),
        )

    async def _run_sync_scope(
        self,
        scope: str,
        triggered_by: str,
        trace_id: str | None,
        runner,
    ) -> dict:
        return await self._scope_execution_use_case().run_scope(
            scope=scope,
            triggered_by=triggered_by,
            trace_id=trace_id,
            runner=runner,
        )

    def _scope_execution_use_case(self) -> SyncScopeExecutionUseCase:
        return SyncScopeExecutionUseCase(
            event_factory=self,
            event_publisher=self,
            metrics=self,
        )

    async def publish_sync_event_via_outbox(self, event: Event) -> None:
        await self._publish_sync_event_via_outbox(event)

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
        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            try:
                ok = await self._event_publisher.publish(event)
                if not ok:
                    raise RuntimeError("event_bus_publish_returned_false")
                await self._mark_sync_event_published(event)
                published += 1
            except Exception as exc:
                await self._mark_sync_event_failed(event, exc)
                failed += 1

        logger.info(
            "sync_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def _publish_sync_event_via_outbox(self, event: Event) -> None:
        """Stage a Sync event in its outbox, then publish after local commit."""
        await self._outbox_store.add(event)
        await self._publish_staged_sync_event(event)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Sync event before EventBus delivery."""
        await self._publish_sync_event_via_outbox(event)
        return True

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a Sync outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _publish_staged_sync_event(self, event: Event) -> None:
        """Publish a Sync event already persisted in the outbox."""
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_sync_event_published(event)
        except Exception as exc:
            await self._mark_sync_event_failed(event, exc)
            raise

    async def _mark_sync_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "sync_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_sync_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an outbox event publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "sync_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )


# Global capability singleton.
agent = SyncModule()


def get_agent() -> SyncModule:
    """Return the current capability instance and support test replacement."""
    return agent
