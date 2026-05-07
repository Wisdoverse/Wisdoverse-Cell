"""SyncModule - scheduled support capability for external work sync."""
import time
from typing import Optional

from pydantic import ValidationError

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.schemas.event_payloads import SyncTriggerPayload
from shared.utils.logger import get_logger

from ..core.engine import SyncEngine
from ..db.database import DatabaseManager, db_manager

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
            db_manager=self._db_manager,
            op_client=get_op_client(),
            bitable=bitable_service,
            event_bus=self._event_bus,
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
        if event.event_type != EventTypes.SYNC_TRIGGER:
            return []

        try:
            payload = SyncTriggerPayload.model_validate(event.payload)
        except ValidationError as exc:
            return [
                self.create_event(
                    EventTypes.SYNC_FAILED,
                    {
                        "scope": "invalid",
                        "error": f"Invalid sync.trigger payload: {exc.errors()[0]['msg']}",
                    },
                    trace_id=event.metadata.trace_id,
                )
            ]

        raw_scope = payload.scope or payload.target or "full"
        scope = self._normalize_sync_scope(raw_scope)
        if scope is None:
            return [
                self.create_event(
                    EventTypes.SYNC_FAILED,
                    {
                        "scope": raw_scope,
                        "error": f"Unsupported sync.trigger scope: {raw_scope}",
                    },
                    trace_id=event.metadata.trace_id,
                )
            ]

        triggered_by = payload.triggered_by or event.source_agent or "event"
        if scope == "openproject":
            await self.trigger_openproject_sync(
                triggered_by=triggered_by,
                trace_id=event.metadata.trace_id,
            )
        elif scope == "feishu_bitable":
            await self.trigger_feishu_bitable_sync(
                triggered_by=triggered_by,
                trace_id=event.metadata.trace_id,
            )
        else:
            await self.trigger_sync(
                triggered_by=triggered_by,
                trace_id=event.metadata.trace_id,
            )
        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "sync_now":
            return await self.trigger_sync(triggered_by="manual")
        if action == "sync_openproject":
            return await self.trigger_openproject_sync(triggered_by="manual")
        if action == "sync_feishu_bitable":
            return await self.trigger_feishu_bitable_sync(triggered_by="manual")
        if action == "status":
            return {
                "status": "running",
                "agent_id": self.agent_id,
                "capabilities": ["openproject_sync", "feishu_bitable_sync"],
            }
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
        return checks

    def _should_decompose(self, project_id: int) -> bool:
        return project_id in self._decompose_project_ids

    def _normalize_sync_scope(self, scope: str) -> str | None:
        normalized = scope.replace("-", "_").lower()
        if normalized in {"full", "openproject", "feishu_bitable"}:
            return normalized
        return None

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
        """Run one sync scope and publish scoped lifecycle events."""
        _start = time.perf_counter()
        start_event = self.create_event(
            EventTypes.SYNC_STARTED,
            {"triggered_by": triggered_by, "scope": scope},
            trace_id=trace_id,
        )
        try:
            await self._event_bus.publish(start_event)
        except Exception as e:
            logger.error("event_publish_failed", event_type=EventTypes.SYNC_STARTED, error=str(e))

        try:
            result = await runner()

            complete_event = self.create_event(
                EventTypes.SYNC_COMPLETED,
                {
                    "synced_count": result.get(
                        "total_processed", result.get("processed", 0)
                    ),
                    "scope": scope,
                    "errors": result.get("op_to_feishu", {}).get("errors", [])
                    + result.get("feishu_to_op", {}).get("errors", [])
                    + result.get("errors", []),
                },
                trace_id=start_event.metadata.trace_id,
            )
            try:
                await self._event_bus.publish(complete_event)
            except Exception as e:
                logger.error(
                    "event_publish_failed",
                    event_type=EventTypes.SYNC_COMPLETED,
                    error=str(e),
                )

            logger.info(
                "sync_completed",
                scope=scope,
                status=result.get("status"),
                synced_count=result.get("total_processed", result.get("processed", 0)),
                error_count=len(
                    result.get("op_to_feishu", {}).get("errors", [])
                    + result.get("feishu_to_op", {}).get("errors", [])
                    + result.get("errors", [])
                ),
            )
            if _metrics_available:
                SYNC_RUNS.labels(
                    triggered_by=triggered_by, status="success",
                ).inc()
                SYNC_DURATION.observe(time.perf_counter() - _start)
                SYNC_RECORDS_PROCESSED.labels(
                    direction=scope,
                ).inc(
                    result.get("total_processed", result.get("processed", 0))
                )
            return result

        except Exception as e:
            fail_event = self.create_event(
                EventTypes.SYNC_FAILED,
                {"error": str(e), "scope": scope},
                trace_id=start_event.metadata.trace_id,
            )
            try:
                await self._event_bus.publish(fail_event)
            except Exception as pub_err:
                logger.error(
                    "event_publish_failed",
                    event_type=EventTypes.SYNC_FAILED,
                    error=str(pub_err),
                )
            logger.error("sync_failed", error=str(e))
            if _metrics_available:
                SYNC_RUNS.labels(triggered_by=triggered_by, status="failed").inc()
            return {"status": "failed", "error": str(e)}


# Global capability singleton.
agent = SyncModule()


def get_agent() -> SyncModule:
    """Return the current capability instance and support test replacement."""
    return agent
