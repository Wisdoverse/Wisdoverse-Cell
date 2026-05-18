"""Application use cases for user-interaction gateway events."""
from __future__ import annotations

from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

logger = get_logger("chat_agent.event_use_cases")


class UserInteractionEventUseCase:
    """Handle user-interaction gateway events outside the service shell."""

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.CHAT_PM_RESPONSE:
            user_id = str(event.payload.get("user_id", ""))
            logger.info(
                "project_management_response_received",
                user_hash=hash_identifier(user_id) if user_id else "",
            )
        elif event.event_type == EventTypes.COORDINATOR_RESPONSE:
            logger.info(
                "coordinator_response_received",
                task_id=event.payload.get("task_id"),
                workflow_id=event.payload.get("workflow_id"),
            )
        return []
