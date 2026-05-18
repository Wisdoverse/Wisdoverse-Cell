"""CoordinatorAgent - system orchestration worker."""
from typing import Any

from shared.config import settings
from shared.core import EventPublisher, unknown_action_error
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.infra.scratchpad import Scratchpad
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..core.event_use_cases import CoordinatorEventUseCase
from ..core.health_ports import CoordinatorHealthStore
from ..core.models import Decision
from ..core.outbox_ports import CoordinatorEventOutboxStore
from ..core.state_ports import CoordinatorStateStorePort
from ..core.think import think as think_fn
from ..db.database import DatabaseManager
from ..db.health_store import SqlAlchemyCoordinatorHealthStore
from ..db.outbox_store import SqlAlchemyCoordinatorEventOutboxStore
from ..db.state_store import CoordinatorStateStore

logger = get_logger("coordinator.agent")


class CoordinatorAgent(BaseAgent):
    """Global orchestration engine."""

    def __init__(
        self,
        *,
        db: DatabaseManager | None = None,
        bus: EventBus | None = None,
        event_publisher: EventPublisher | None = None,
        outbox_store: CoordinatorEventOutboxStore | None = None,
        state_store: CoordinatorStateStorePort | None = None,
        health_store: CoordinatorHealthStore | None = None,
    ):
        super().__init__(
            agent_id="coordinator",
            agent_name="Coordinator",
            subscribed_events=[
                EventTypes.COORDINATOR_COMMAND,
                EventTypes.TASK_NOTIFICATION,
                EventTypes.TASK_PROGRESS,
                EventTypes.PM_PRD_READY,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_DECOMPOSITION_FAILED,
                EventTypes.ANALYSIS_RISK_DETECTED,
            ],
            published_events=[
                EventTypes.COORDINATOR_RESPONSE,
                EventTypes.COORDINATOR_DISPATCH,
                EventTypes.PM_TASKS_READY_FOR_DEV,
                EventTypes.QA_RUN_REQUESTED,
            ],
        )
        self._scratchpad = Scratchpad()
        self._state_store: CoordinatorStateStorePort = state_store or CoordinatorStateStore()
        self._llm = llm_gateway
        self._db_manager = db
        self._health_store = health_store
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store
        if self._outbox_store is None and self._db_manager is not None:
            self._outbox_store = SqlAlchemyCoordinatorEventOutboxStore(
                self._db_manager
            )

    async def startup(self) -> None:
        await self._scratchpad.initialize()
        if self._db_manager is not None:
            if settings.app_env == "development":
                await self._db_manager.create_tables()
                logger.info("coordinator_db_initialized")
        await self._event_bus.connect()
        logger.info("coordinator_started")

    async def shutdown(self) -> None:
        await self._event_bus.disconnect()
        if self._db_manager is not None:
            await self._db_manager.close()
        logger.info("coordinator_stopped")

    async def handle_event(self, event: Event) -> list[Event]:
        """Single entry point for all events."""
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> CoordinatorEventUseCase:
        return CoordinatorEventUseCase(
            scratchpad=self._scratchpad,
            state_store=self._state_store,
            thinker=self._think,
        )

    async def handle_request(self, request: dict) -> dict:
        """Handle governance API requests."""
        result = await self.handle_standard_request(request)
        if result is not None:
            return result
        return unknown_action_error(action=request.get("action"))

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the coordinator runtime boundary."""
        checks = {
            "scratchpad": self._scratchpad.is_initialized(),
            "state_store": self._state_store is not None,
            "llm_gateway": self._llm is not None,
        }
        if self._db_manager is not None:
            checks["database"] = False
            checks["database"] = await self._get_health_store().is_database_ready()
        return checks

    def _get_health_store(self) -> CoordinatorHealthStore:
        if self._health_store is None:
            if self._db_manager is None:
                raise RuntimeError("coordinator_database_not_started")
            self._health_store = SqlAlchemyCoordinatorHealthStore(self._db_manager)
        return self._health_store

    async def publish_pending_coordinator_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        """Retry pending Coordinator outbox events."""
        if self._outbox_store is None:
            raise RuntimeError("coordinator_outbox_store_not_started")

        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            if await self._publish_staged_coordinator_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "coordinator_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Coordinator event before EventBus delivery."""
        if self._outbox_store is None:
            raise RuntimeError("coordinator_outbox_store_not_started")
        await self._outbox_store.add(event)
        return await self._publish_staged_coordinator_event(event)

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a Coordinator outbox row."""
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

    async def _publish_staged_coordinator_event(self, event: Event) -> bool:
        """Publish one event already persisted in the Coordinator outbox."""
        try:
            await self._event_bus.connect()
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_coordinator_event_published(event)
            return True
        except Exception as exc:
            await self._mark_coordinator_event_failed(event, exc)
            logger.error(
                "coordinator_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    async def _mark_coordinator_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published Coordinator event."""
        if self._outbox_store is None:
            return
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "coordinator_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_coordinator_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a Coordinator publish attempt."""
        if self._outbox_store is None:
            return
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "coordinator_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

    async def _think(self, context: dict[str, Any]) -> list[Decision]:
        """LLM synthesis — calls think engine with current LLM gateway."""
        return await think_fn(context, llm=self._llm)
