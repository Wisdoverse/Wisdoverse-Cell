"""Application facade for the chat-agent service shell."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.schemas.event import Event, EventTypes

from .chat_ports import ChatHistoryStore
from .daily_progress_queries import DailyProgressQueryService
from .daily_tasks import collect_evening_progress, dispatch_morning_tasks
from .event_ports import ChatAgentEventOutboxStore
from .event_use_cases import ChatAgentEventUseCase
from .health_ports import ChatAgentHealthStore
from .health_use_cases import ChatAgentHealthUseCase
from .outbox_delivery_use_cases import ChatAgentOutboxDeliveryUseCase
from .request_use_cases import ChatAgentRequestUseCase

StandardRequestHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
AsyncCommand = Callable[[], Awaitable[Any]]


class ChatAgentApplicationFacade:
    """Coordinate chat-agent application use cases behind the runtime boundary."""

    def __init__(
        self,
        *,
        agent_id: str,
        standard_request_handler: StandardRequestHandler,
        chat_provider: Callable[[], Any],
        history_store: ChatHistoryStore,
        health_store: ChatAgentHealthStore,
        outbox_store: ChatAgentEventOutboxStore,
        event_bus: Any,
        event_publisher: Any,
        daily_progress_queries_provider: Callable[
            [], DailyProgressQueryService | None
        ] = lambda: None,
        dispatch_morning_tasks_command: AsyncCommand = dispatch_morning_tasks,
        collect_evening_progress_command: AsyncCommand = collect_evening_progress,
    ) -> None:
        self._agent_id = agent_id
        self._standard_request_handler = standard_request_handler
        self._chat_provider = chat_provider
        self._history_store = history_store
        self._health_store = health_store
        self._outbox_store = outbox_store
        self._event_bus = event_bus
        self._event_publisher = event_publisher
        self._daily_progress_queries_provider = daily_progress_queries_provider
        self._dispatch_morning_tasks = dispatch_morning_tasks_command
        self._collect_evening_progress = collect_evening_progress_command

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> ChatAgentEventUseCase:
        return ChatAgentEventUseCase()

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        standard_response = await self._standard_request_handler(request)
        if standard_response is not None:
            return standard_response
        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> ChatAgentRequestUseCase:
        return ChatAgentRequestUseCase(
            chat=self._chat_provider(),
            history_store=self._history_store,
            dispatch_morning_tasks=self._dispatch_morning_tasks,
            collect_evening_progress=self._collect_evening_progress,
            daily_progress_queries=self._daily_progress_queries_provider(),
        )

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> ChatAgentHealthUseCase:
        return ChatAgentHealthUseCase(
            health_store=self._health_store,
            chat_service=self._chat_provider(),
        )

    async def publish_sync_trigger(self, *, scope: str) -> bool:
        """Publish a sync trigger command through the chat-agent outbox."""
        event = Event.create(
            event_type=EventTypes.SYNC_TRIGGER,
            source_agent=self._agent_id,
            payload={"triggered_by": "chat_tool", "scope": scope},
        )
        return await self.publish_event_via_outbox(event)

    async def publish_pending_chat_agent_events(
        self,
        limit: int = 100,
    ) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> ChatAgentOutboxDeliveryUseCase:
        return ChatAgentOutboxDeliveryUseCase(
            outbox_store=self._outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )
