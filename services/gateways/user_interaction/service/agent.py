"""User interaction gateway service for chat and Feishu webhook requests."""
from typing import Optional

from shared.config import settings as app_settings
from shared.control_plane import ApprovalGateService
from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.cards.tools import FeishuToolCardRenderer
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..core.card_ports import configure_tool_card_renderer
from ..core.chat_ports import ChatHistoryStore
from ..core.chat_service import ChatService
from ..core.daily_tasks import (
    DailyTaskDependencies,
    collect_evening_progress,
    configure_daily_task_dependencies,
    dispatch_morning_tasks,
)
from ..core.event_ports import UserInteractionEventOutboxStore
from ..core.event_use_cases import UserInteractionEventUseCase
from ..core.health_ports import UserInteractionHealthStore
from ..core.health_use_cases import UserInteractionHealthUseCase
from ..core.ops_logger import configure_operation_log_store
from ..core.request_use_cases import UserInteractionRequestUseCase
from ..core.tools import ToolDependencies, configure_tool_dependencies
from ..db.chat_store import SqlAlchemyChatHistoryStore
from ..db.daily_progress_store import SqlAlchemyDailyProgressStore
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyUserInteractionHealthStore
from ..db.operation_log_store import SqlAlchemyCardOperationLogStore
from ..db.outbox_store import SqlAlchemyUserInteractionEventOutboxStore
from .config_factory import build_user_interaction_core_config

logger = get_logger("chat_agent.service")


class ChatAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        outbox_store: UserInteractionEventOutboxStore | None = None,
        history_store: ChatHistoryStore | None = None,
        health_store: UserInteractionHealthStore | None = None,
    ):
        super().__init__(
            agent_id="chat-agent",
            agent_name="User Interaction Gateway",
            subscribed_events=[
                EventTypes.CHAT_PM_RESPONSE,
                EventTypes.COORDINATOR_RESPONSE,
            ],
            published_events=[
                EventTypes.CHAT_PM_QUERY,
                EventTypes.COORDINATOR_COMMAND,
                EventTypes.SYNC_TRIGGER,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store or SqlAlchemyUserInteractionEventOutboxStore(
            self._db_manager
        )
        self._history_store = history_store or SqlAlchemyChatHistoryStore(self._db_manager)
        self._health_store = health_store or SqlAlchemyUserInteractionHealthStore(
            self._db_manager
        )
        self._chat: ChatService | None = None

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        core_config = build_user_interaction_core_config()
        feishu_client = get_feishu_client()
        card_renderer = FeishuToolCardRenderer()
        daily_progress_store = SqlAlchemyDailyProgressStore(self._db_manager)
        operation_log_store = SqlAlchemyCardOperationLogStore(self._db_manager)
        configure_operation_log_store(operation_log_store)
        configure_tool_card_renderer(card_renderer)
        configure_tool_dependencies(
            ToolDependencies(
                op_client=get_op_client(),
                bitable=bitable_service,
                messenger=feishu_client,
                contact_lookup=feishu_client,
                card_renderer=card_renderer,
                event_publisher=self,
                card_operation_store=operation_log_store,
                daily_progress_store=daily_progress_store,
                approval_gate=ApprovalGateService(source_agent_id=self.agent_id),
                config=core_config,
            )
        )
        configure_daily_task_dependencies(
            DailyTaskDependencies(
                bitable=bitable_service,
                messenger=feishu_client,
                dispatch_llm=llm_gateway,
                progress_store=daily_progress_store,
                config=core_config,
            )
        )
        self._chat = ChatService(
            config=core_config,
            llm=llm_gateway,
            history_store=self._history_store,
            daily_progress_store=daily_progress_store,
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

    def _event_use_case(self) -> UserInteractionEventUseCase:
        return UserInteractionEventUseCase()

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> UserInteractionRequestUseCase:
        return UserInteractionRequestUseCase(
            chat=self._chat,
            history_store=self._history_store,
            dispatch_morning_tasks=dispatch_morning_tasks,
            collect_evening_progress=collect_evening_progress,
        )

    async def publish_sync_trigger(self, *, scope: str) -> bool:
        """Publish a sync trigger command through the gateway outbox."""
        event = Event.create(
            event_type=EventTypes.SYNC_TRIGGER,
            source_agent=self.agent_id,
            payload={"triggered_by": "chat_tool", "scope": scope},
        )
        return await self._publish_gateway_event_via_outbox(event)

    async def publish_pending_user_interaction_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        """Retry pending user-interaction gateway outbox events."""
        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            if await self._publish_staged_gateway_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "chat_agent_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def _publish_gateway_event_via_outbox(self, event: Event) -> bool:
        """Stage a gateway event in its outbox, then publish after local commit."""
        await self._outbox_store.add(event)
        return await self._publish_staged_gateway_event(event)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced user-interaction event before delivery."""
        return await self._publish_gateway_event_via_outbox(event)

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a gateway outbox row."""
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

    async def _publish_staged_gateway_event(self, event: Event) -> bool:
        """Publish an event already persisted in the gateway outbox."""
        try:
            await self._event_bus.connect()
            published = await self._event_publisher.publish(event)
            if not published:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_gateway_event_published(event)
            return True
        except Exception as exc:
            await self._mark_gateway_event_failed(event, exc)
            logger.warning(
                "chat_agent_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    async def _mark_gateway_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published gateway outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "chat_agent_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_gateway_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a gateway outbox publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "chat_agent_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._health_use_case().check()

    def _health_use_case(self) -> UserInteractionHealthUseCase:
        return UserInteractionHealthUseCase(
            health_store=self._health_store,
            chat_service=self._chat,
        )


agent = ChatAgent()


def get_agent() -> ChatAgent:
    return agent
