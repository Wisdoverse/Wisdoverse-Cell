"""Chat Agent runtime service."""
from __future__ import annotations

from typing import Optional

from shared.config import settings as app_settings
from shared.control_plane import ApprovalGateService
from shared.core import EventPublisher
from shared.infra.conversation_engine import ConversationConfig, ConversationEngine
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.cards.tools import FeishuToolCardRenderer
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.application_facade import ChatAgentApplicationFacade
from ..core.card_ports import configure_tool_card_renderer
from ..core.chat_ports import ChatHistoryStore
from ..core.chat_service import ChatService
from ..core.daily_progress_queries import DailyProgressQueryService
from ..core.daily_tasks import (
    DailyTaskDependencies,
    configure_daily_task_dependencies,
)
from ..core.event_ports import ChatAgentEventOutboxStore
from ..core.health_ports import ChatAgentHealthStore
from ..core.ops_logger import configure_operation_log_store
from ..core.tools import ToolDependencies, configure_tool_dependencies
from ..db.chat_store import SqlAlchemyChatHistoryStore
from ..db.daily_progress_store import SqlAlchemyDailyProgressStore
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyChatAgentHealthStore
from ..db.operation_log_store import SqlAlchemyCardOperationLogStore
from ..db.outbox_store import SqlAlchemyChatAgentEventOutboxStore
from .config_factory import build_chat_agent_core_config

logger = get_logger("chat_agent.service")


class ChatAgent(BaseAgent):
    """Real chat-agent runtime.

    Owns conversation history, card-operation logs, daily-progress state,
    chat tool orchestration, and the chat-agent outbox. The
    user-interaction gateway calls this runtime through HTTP adapters.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        outbox_store: ChatAgentEventOutboxStore | None = None,
        history_store: ChatHistoryStore | None = None,
        health_store: ChatAgentHealthStore | None = None,
    ) -> None:
        super().__init__(
            agent_id="chat-agent",
            agent_name="Chat Agent",
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
        self._outbox_store = outbox_store or SqlAlchemyChatAgentEventOutboxStore(
            self._db_manager
        )
        self._history_store = history_store or SqlAlchemyChatHistoryStore(
            self._db_manager
        )
        self._health_store = health_store or SqlAlchemyChatAgentHealthStore(
            self._db_manager
        )
        self._chat: ChatService | None = None
        self._daily_progress_queries: DailyProgressQueryService | None = None
        self._application = ChatAgentApplicationFacade(
            agent_id=self.agent_id,
            standard_request_handler=self.handle_standard_request,
            chat_provider=lambda: self._chat,
            history_store=self._history_store,
            health_store=self._health_store,
            outbox_store=self._outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
            daily_progress_queries_provider=lambda: self._daily_progress_queries,
        )

    async def startup(self) -> None:
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        core_config = build_chat_agent_core_config()
        feishu_client = get_feishu_client()
        card_renderer = FeishuToolCardRenderer()
        daily_progress_store = SqlAlchemyDailyProgressStore(self._db_manager)
        self._daily_progress_queries = DailyProgressQueryService(daily_progress_store)
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

        def _engine_factory(
            *,
            system_prompt: str,
            history,
            tools_provider,
            tool_executor,
            compressor,
            max_tool_calls: int,
            agent_id: str,
        ):
            engine_config = ConversationConfig(
                model=core_config.chat_model,
                system_prompt=system_prompt,
                tools=tools_provider,
                max_tool_calls=max_tool_calls,
                agent_id=agent_id,
            )
            return ConversationEngine(
                engine_config,
                llm_gateway=llm_gateway,
                compressor=compressor,
                tool_executor=tool_executor,
                messages=history,
            )

        self._chat = ChatService(
            config=core_config,
            llm=llm_gateway,
            history_store=self._history_store,
            daily_progress_store=daily_progress_store,
            engine_factory=_engine_factory,
        )

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self) -> None:
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        return await self._application.handle_request(request)

    async def publish_sync_trigger(self, *, scope: str) -> bool:
        """Publish a sync trigger command through the chat-agent outbox."""
        return await self._application.publish_sync_trigger(scope=scope)

    async def publish_pending_chat_agent_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        """Retry pending chat-agent outbox events."""
        return await self._application.publish_pending_chat_agent_events(limit=limit)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced chat-agent event before delivery."""
        return await self._application.publish_event_via_outbox(event)

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        return await self._application.health_check()


agent = ChatAgent()


def get_agent() -> ChatAgent:
    return agent
