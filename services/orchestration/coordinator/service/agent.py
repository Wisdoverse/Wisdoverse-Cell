"""CoordinatorAgent - system orchestration worker."""
from typing import Any

from shared.config import settings
from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.infra.scratchpad import Scratchpad
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.application_facade import CoordinatorApplicationFacade
from ..core.health_ports import CoordinatorHealthStore
from ..core.models import Decision
from ..core.outbox_ports import CoordinatorEventOutboxStore
from ..core.state_ports import CoordinatorStateStorePort
from ..core.think import think as think_fn
from ..db.database import DatabaseManager
from ..db.health_store import SqlAlchemyCoordinatorHealthStore
from ..db.in_memory_unit_of_work import in_memory_coordinator_uow
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
        self._application = CoordinatorApplicationFacade(
            standard_request_handler=self.handle_standard_request,
            scratchpad_provider=lambda: self._scratchpad,
            state_store_provider=lambda: self._state_store,
            thinker_provider=lambda: self._think,
            llm_gateway_provider=lambda: self._llm,
            database_enabled=self._db_manager is not None,
            health_store_provider=self._get_health_store_if_configured,
            outbox_store_provider=lambda: self._outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
            uow_factory_provider=lambda: self._build_uow_factory(),
        )

    def _build_uow_factory(self):
        """Build a CoordinatorUnitOfWorkFactory from the current stores."""
        outbox = self._outbox_store
        if outbox is None:
            return None
        state_store = self._state_store

        def factory():
            return in_memory_coordinator_uow(
                state_store=state_store, outbox=outbox
            )

        return factory

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
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        """Handle governance API requests."""
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the coordinator runtime boundary."""
        return await self._application.health_check()

    def _get_health_store_if_configured(self) -> CoordinatorHealthStore | None:
        if self._db_manager is None:
            return None
        return self._get_health_store()

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
        return await self._application.publish_pending_coordinator_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Coordinator event before EventBus delivery."""
        return await self._application.publish_event_via_outbox(event)

    async def _think(self, context: dict[str, Any]) -> list[Decision]:
        """LLM synthesis — calls think engine with current LLM gateway."""
        return await think_fn(context, llm=self._llm)
