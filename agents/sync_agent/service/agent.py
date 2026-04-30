"""
SyncAgent - OpenProject ↔ 飞书同步 Agent

定时触发同步，发布 sync.completed 事件驱动下游 Agent。
"""
import time
from typing import Optional

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.engine import SyncEngine
from ..db.database import DatabaseManager, db_manager

try:
    from ..app.metrics import SYNC_DURATION, SYNC_RECORDS_PROCESSED, SYNC_RUNS
    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("sync_agent.service")


class SyncAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
    ):
        super().__init__(
            agent_id="sync-agent",
            agent_name="同步Agent",
            subscribed_events=[],
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
        )

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        # Close OpenProject httpx client
        if self._sync_engine and self._sync_engine._op_client:
            await self._sync_engine._op_client.close()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "sync_now":
            return await self.trigger_sync(triggered_by="manual")
        if action == "status":
            return {"status": "running", "agent_id": self.agent_id}
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

    async def trigger_sync(self, triggered_by: str = "scheduler") -> dict:
        """触发同步并发布事件"""
        _start = time.perf_counter()
        start_event = self.create_event(
            EventTypes.SYNC_STARTED,
            {"triggered_by": triggered_by},
        )
        try:
            await self._event_bus.publish(start_event)
        except Exception as e:
            logger.error("event_publish_failed", event_type=EventTypes.SYNC_STARTED, error=str(e))

        try:
            result = await self._sync_engine.full_sync()

            complete_event = self.create_event(
                EventTypes.SYNC_COMPLETED,
                {
                    "synced_count": result.get("total_processed", 0),
                    "errors": result.get("op_to_feishu", {}).get("errors", [])
                    + result.get("feishu_to_op", {}).get("errors", []),
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

            logger.info("sync_completed", result=result)
            if _metrics_available:
                SYNC_RUNS.labels(
                    triggered_by=triggered_by, status="success",
                ).inc()
                SYNC_DURATION.observe(time.perf_counter() - _start)
                SYNC_RECORDS_PROCESSED.labels(
                    direction="full",
                ).inc(result.get("total_processed", 0))
            return result

        except Exception as e:
            fail_event = self.create_event(
                EventTypes.SYNC_FAILED,
                {"error": str(e)},
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


# 全局 Agent 实例（单例）
agent = SyncAgent()


def get_agent() -> SyncAgent:
    """获取当前 Agent 实例（支持测试时替换）"""
    return agent
