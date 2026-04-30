"""Event classifier for Coordinator Agent."""
from dataclasses import dataclass
from typing import Union

from shared.schemas.coordinator import (
    AgentProgress,
    CoordinatorCommand,
    TaskNotification,
)
from shared.schemas.event import Event, EventTypes


@dataclass
class ClassifiedEvent:
    """Typed event for Coordinator processing."""

    kind: str  # "command" | "notification" | "progress" | "event"
    data: Union[CoordinatorCommand, TaskNotification, AgentProgress, Event]


def classify_event(event: Event) -> ClassifiedEvent:
    """Classify an EventBus event into a Coordinator-internal type."""
    if event.event_type == EventTypes.COORDINATOR_COMMAND:
        return ClassifiedEvent(
            kind="command",
            data=CoordinatorCommand(**event.payload),
        )
    if event.event_type == EventTypes.TASK_NOTIFICATION:
        return ClassifiedEvent(
            kind="notification",
            data=TaskNotification(**event.payload),
        )
    if event.event_type == EventTypes.TASK_PROGRESS:
        return ClassifiedEvent(
            kind="progress",
            data=AgentProgress(**event.payload),
        )
    return ClassifiedEvent(kind="event", data=event)
