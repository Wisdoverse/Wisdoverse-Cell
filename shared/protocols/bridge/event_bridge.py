"""
EventBus to A2A Bridge

Bridges between the internal EventBus and A2A protocol for external agent communication.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from shared.core import EventPublisher
from shared.infra.event_publisher import EventBusEventPublisher
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..a2a.client.client import A2AClient
from ..a2a.models import DataPart, FilePart, Message, Task, TaskStatus, TextPart
from ..a2a.registry.registry import AgentRegistry

logger = get_logger("protocols.event_bridge")

_TASK_STATUS_EVENT_TYPES = {
    TaskStatus.SUBMITTED: EventTypes.A2A_TASK_SUBMITTED,
    TaskStatus.WORKING: EventTypes.A2A_TASK_WORKING,
    TaskStatus.INPUT_REQUIRED: EventTypes.A2A_TASK_INPUT_REQUIRED,
    TaskStatus.COMPLETED: EventTypes.A2A_TASK_COMPLETED,
    TaskStatus.FAILED: EventTypes.A2A_TASK_FAILED,
    TaskStatus.CANCELED: EventTypes.A2A_TASK_CANCELED,
}

class EventA2AMapping:
    """Mapping configuration for Event <-> A2A conversion."""

    def __init__(
        self,
        event_type: str,
        target_agent_id: str,
        skill_id: str | None = None,
        transform: Callable[[Event], dict[str, Any]] | None = None,
    ):
        """
        Configure mapping from Event type to A2A target.

        Args:
            event_type: The event type to map.
            target_agent_id: The A2A agent ID to send to.
            skill_id: Optional skill ID for the target agent.
            transform: Optional function to transform event payload.
        """
        self.event_type = event_type
        self.target_agent_id = target_agent_id
        self.skill_id = skill_id
        self.transform = transform


class EventBusA2ABridge:
    """
    Bridge between EventBus and A2A protocol.

    Enables:
    - Routing internal Events to external A2A agents
    - Converting A2A task results back to Events
    - Maintaining trace_id correlation across protocols
    """

    def __init__(
        self,
        registry: AgentRegistry,
        event_bus=None,
        source_agent_id: str = "a2a-bridge",
        event_publisher: EventPublisher | None = None,
    ):
        """
        Initialize the bridge.

        Args:
            registry: A2A agent registry for discovering agents.
            event_bus: Optional EventBus for publishing response events.
            source_agent_id: Agent ID to use when creating response events.
            event_publisher: Optional outbound event publisher port. Prefer this
                over event_bus for new code.
        """
        self._registry = registry
        self._event_publisher = event_publisher
        if self._event_publisher is None and event_bus is not None:
            self._event_publisher = EventBusEventPublisher(event_bus)
        self._source_agent_id = source_agent_id
        self._mappings: dict[str, EventA2AMapping] = {}
        self._active_clients: dict[str, A2AClient] = {}
        self._lock = asyncio.Lock()

    # ============ Configuration ============

    def add_mapping(self, mapping: EventA2AMapping) -> None:
        """
        Add an event to A2A mapping.

        Args:
            mapping: The mapping configuration.
        """
        self._mappings[mapping.event_type] = mapping

    def remove_mapping(self, event_type: str) -> bool:
        """
        Remove an event mapping.

        Args:
            event_type: The event type to remove.

        Returns:
            True if mapping was removed.
        """
        if event_type in self._mappings:
            del self._mappings[event_type]
            return True
        return False

    # ============ Event -> A2A ============

    def event_to_a2a_message(
        self,
        event: Event,
        mapping: EventA2AMapping | None = None,
    ) -> Message:
        """
        Convert an Event to an A2A Message.

        Args:
            event: The event to convert.
            mapping: Optional mapping for transformation.

        Returns:
            A2A Message.
        """
        # Apply transformation if provided
        if mapping and mapping.transform:
            payload = mapping.transform(event)
        else:
            payload = event.payload

        # Create message with event metadata
        parts: list[TextPart | FilePart | DataPart] = [
            DataPart(
                data={
                    "event_type": event.event_type,
                    "source_agent": event.source_agent,
                    "payload": payload,
                    "trace_id": event.metadata.trace_id,
                    "event_id": event.event_id,
                }
            )
        ]

        # Add text summary if payload has a message field
        if "message" in payload:
            parts.insert(0, TextPart(text=str(payload["message"])))

        return Message(
            role="user",
            parts=parts,
            metadata={
                "source": "event_bridge",
                "event_type": event.event_type,
                "trace_id": event.metadata.trace_id,
            },
        )

    async def route_event_to_a2a(
        self,
        event: Event,
        target_agent_id: str | None = None,
        wait_for_result: bool = True,
        publish_result: bool = True,
    ) -> Task | None:
        """
        Route an Event to an A2A agent.

        Args:
            event: The event to route.
            target_agent_id: Optional target agent (uses mapping if not provided).
            wait_for_result: Whether to wait for task completion.
            publish_result: Whether this method should publish terminal result
                events itself. Runtime handle_event() disables this and returns
                the event to the runtime publisher instead.

        Returns:
            The A2A Task result if waiting, None otherwise.
        """
        # Determine target
        mapping = self._mappings.get(event.event_type)
        agent_id = target_agent_id or (mapping.target_agent_id if mapping else None)

        if not agent_id:
            raise ValueError(
                f"No target agent for event type: {event.event_type}"
            )

        # Get or create client
        client = await self._get_client(agent_id)

        # Convert event to message
        message = self.event_to_a2a_message(event, mapping)

        # Use trace_id as context_id for correlation
        context_id = event.metadata.trace_id

        if wait_for_result:
            # Send and wait for result
            task = await client.send_message(message, context_id)

            # Publish result event if requested by direct callers
            if publish_result and task.is_terminal():
                await self._publish_result_event(event, task)

            return task
        else:
            # Fire and forget with streaming
            asyncio.create_task(
                self._route_streaming(client, message, context_id, event)
            )
            return None

    async def _route_streaming(
        self,
        client: A2AClient,
        message: Message,
        context_id: str | None,
        original_event: Event,
    ) -> None:
        """Route event with streaming and publish updates."""
        try:
            async for task in client.send_message_streaming(message, context_id):
                if task.is_terminal():
                    await self._publish_result_event(original_event, task)
        except Exception as e:
            await self._publish_error_event(original_event, e)

    # ============ A2A -> Event ============

    def a2a_task_to_event(
        self,
        task: Task,
        original_event: Event | None = None,
    ) -> Event:
        """
        Convert an A2A Task result to an Event.

        Args:
            task: The A2A task to convert.
            original_event: Optional original event for correlation.

        Returns:
            Event with task result.
        """
        # Determine event type based on task status
        event_type = _TASK_STATUS_EVENT_TYPES[task.status.state]

        # Extract result data
        result_data: dict[str, Any] = {
            "task_id": task.id,
            "context_id": task.context_id,
            "status": task.status.state.value,
        }

        # Add artifacts if present
        if task.artifacts:
            result_data["artifacts"] = [
                {
                    "artifact_id": a.artifact_id,
                    "name": a.name,
                    "description": a.description,
                }
                for a in task.artifacts
            ]

        # Add status message if present
        if task.status.message:
            text = task.status.message.get_text_content()
            if text:
                result_data["message"] = text

        # Correlation
        trace_id = original_event.metadata.trace_id if original_event else None
        correlation_id = original_event.event_id if original_event else None

        return Event(
            event_type=event_type,
            source_agent=self._source_agent_id,
            payload=result_data,
            metadata=EventMetadata(
                trace_id=trace_id,
                correlation_id=correlation_id,
            ),
        )

    async def _publish_result_event(
        self,
        original_event: Event,
        task: Task,
    ) -> None:
        """Publish task result as event."""
        result_event = self.a2a_task_to_event(task, original_event)
        await self._publish_event(result_event)

    async def _publish_error_event(
        self,
        original_event: Event,
        error: Exception,
    ) -> None:
        """Publish error as event."""
        error_event = Event(
            event_type=EventTypes.A2A_TASK_ERROR,
            source_agent=self._source_agent_id,
            payload={
                "error": str(error),
                "original_event_type": original_event.event_type,
            },
            metadata=EventMetadata(
                trace_id=original_event.metadata.trace_id,
                correlation_id=original_event.event_id,
            ),
        )
        await self._publish_event(error_event)

    async def _publish_event(self, event: Event) -> bool:
        """Publish through the configured outbound port."""
        if self._event_publisher is None:
            logger.warning(
                "a2a_bridge_event_publish_skipped",
                event_id=event.event_id,
                event_type=event.event_type,
                reason="event_publisher_not_configured",
            )
            return False

        try:
            published = await self._event_publisher.publish(event)
        except Exception as exc:
            logger.warning(
                "a2a_bridge_event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False

        if not published:
            logger.warning(
                "a2a_bridge_event_publish_rejected",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return False
        return True

    # ============ Client Management ============

    async def _get_client(self, agent_id: str) -> A2AClient:
        """Get or create A2A client for an agent."""
        async with self._lock:
            if agent_id not in self._active_clients:
                client = await self._registry.get_client(agent_id)
                self._active_clients[agent_id] = client
            return self._active_clients[agent_id]

    async def close_all_clients(self) -> None:
        """Close all active clients."""
        async with self._lock:
            for client in self._active_clients.values():
                await client.disconnect()
            self._active_clients.clear()

    # ============ Event Handler ============

    async def handle_event(self, event: Event) -> list[Event]:
        """
        Handle an event by routing to A2A if mapped.

        This method can be used as an event handler in the event loop.

        Args:
            event: The event to handle.

        Returns:
            List of response events (may be empty for async routing).
        """
        if event.event_type not in self._mappings:
            return []

        try:
            task = await self.route_event_to_a2a(
                event,
                wait_for_result=True,
                publish_result=False,
            )
            if task:
                return [self.a2a_task_to_event(task, event)]
        except Exception as e:
            return [
                Event(
                    event_type=EventTypes.A2A_TASK_ERROR,
                    source_agent=self._source_agent_id,
                    payload={
                        "error": str(e),
                        "original_event_type": event.event_type,
                    },
                    metadata=EventMetadata(
                        trace_id=event.metadata.trace_id,
                        correlation_id=event.event_id,
                    ),
                )
            ]

        return []


async def create_event_bridge(
    registry: AgentRegistry,
    event_bus=None,
    mappings: list[EventA2AMapping] | None = None,
    event_publisher: EventPublisher | None = None,
) -> EventBusA2ABridge:
    """
    Factory function to create and configure an EventBus-A2A bridge.

    Args:
        registry: A2A agent registry.
        event_bus: Optional EventBus for publishing responses.
        mappings: Optional list of event mappings to configure.
        event_publisher: Optional event publisher port for bridge responses.

    Returns:
        Configured EventBusA2ABridge.
    """
    bridge = EventBusA2ABridge(
        registry,
        event_bus=event_bus,
        event_publisher=event_publisher,
    )

    if mappings:
        for mapping in mappings:
            bridge.add_mapping(mapping)

    return bridge
