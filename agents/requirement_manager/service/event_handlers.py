"""
Event handlers.

Dispatches handling logic by event type. When the agent subscribes to events,
received events are routed through this module to the corresponding handler.
"""
from typing import TYPE_CHECKING

from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from .agent import RequirementManagerAgent

logger = get_logger("requirement-manager.event_handlers")


# Subscribed event types.
SUBSCRIBED_EVENTS = [
    EventTypes.PROJECT_CREATED,
    EventTypes.PROJECT_UPDATED,
    EventTypes.SPRINT_STARTED,
    EventTypes.SPRINT_COMPLETED,
    EventTypes.MEETING_UPLOADED,
    EventTypes.COORDINATOR_DISPATCH,
]


async def dispatch_event(agent: "RequirementManagerAgent", event: Event) -> list[Event]:
    """
    Event dispatcher.

    Routes events to the corresponding handler by event type.

    Args:
        agent: Agent instance.
        event: Received event.

    Returns:
        New events produced while handling the input event.
    """
    # Handle coordinator.dispatch inline (no dedicated handler function needed)
    if event.event_type == EventTypes.COORDINATOR_DISPATCH:
        if event.payload.get("target_agent") == "requirement-manager":
            logger.info(
                "coordinator_dispatch_received",
                task_id=event.payload.get("task_id"),
                workflow_id=event.payload.get("workflow_id"),
                instruction=event.payload.get("instruction"),
            )
        return []

    handlers = {
        EventTypes.PROJECT_CREATED: handle_project_created,
        EventTypes.PROJECT_UPDATED: handle_project_updated,
        EventTypes.SPRINT_STARTED: handle_sprint_started,
        EventTypes.SPRINT_COMPLETED: handle_sprint_completed,
        EventTypes.MEETING_UPLOADED: handle_meeting_uploaded,
    }

    handler = handlers.get(event.event_type)

    if handler is None:
        logger.warning(
            "unhandled_event_type",
            event_type=event.event_type,
            event_id=event.event_id
        )
        return []

    logger.info(
        "handling_event",
        event_type=event.event_type,
        event_id=event.event_id,
        trace_id=event.metadata.trace_id
    )

    try:
        return await handler(agent, event)
    except Exception as e:
        logger.error(
            "event_handler_failed",
            event_type=event.event_type,
            event_id=event.event_id,
            error=str(e)
        )
        raise


# ========== Event Handlers ==========

async def handle_project_created(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    Handle project-created events.

    When a new project is created, associate related open requirements.
    """
    payload = event.payload
    project_id = payload.get("project_id")
    project_name = payload.get("name", "")
    keywords = payload.get("keywords", [])

    if not project_id:
        logger.warning("project_created_missing_id", event_id=event.event_id)
        return []

    logger.info(
        "project_created_received",
        project_id=project_id,
        project_name=project_name,
        keywords=keywords
    )

    # Find potentially related requirements using keywords.
    # Automatic association can be implemented later.
    # async with agent._db_manager.session() as session:
    #     repo = RequirementRepository(session)
    #     # Search requirements that contain project keywords.
    #     # Automatically add project tags.

    return []


async def handle_project_updated(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    Handle project-updated events.

    When project information changes, related requirement status may need updates.
    """
    payload = event.payload
    project_id = payload.get("project_id")
    changes = payload.get("changes", {})

    logger.info(
        "project_updated_received",
        project_id=project_id,
        changes=list(changes.keys())
    )

    # Future implementation: update requirements based on project status changes.
    return []


async def handle_sprint_started(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    Handle sprint-started events.

    When a new sprint starts:
    1. Highlight requirements related to the current sprint.
    2. Send reminders to Feishu groups.
    """
    payload = event.payload
    sprint_id = payload.get("sprint_id")
    sprint_name = payload.get("name", "")
    requirement_ids = payload.get("requirement_ids", [])
    _ = payload.get("start_date")  # reserved for future sprint date filtering
    _ = payload.get("end_date")

    logger.info(
        "sprint_started_received",
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        requirement_count=len(requirement_ids)
    )

    # Future implementation:
    # 1. Mark requirements as "current sprint".
    # 2. Send Feishu notifications.

    return []


async def handle_sprint_completed(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    Handle sprint-completed events.

    When a sprint is completed:
    1. Summarize requirement completion.
    2. Generate a sprint report.
    """
    payload = event.payload
    sprint_id = payload.get("sprint_id")
    completed_requirements = payload.get("completed_requirement_ids", [])
    incomplete_requirements = payload.get("incomplete_requirement_ids", [])

    logger.info(
        "sprint_completed_received",
        sprint_id=sprint_id,
        completed_count=len(completed_requirements),
        incomplete_count=len(incomplete_requirements)
    )

    # Future implementation:
    # 1. Generate sprint summary.
    # 2. Mark incomplete requirements for the next sprint.

    return []


async def handle_meeting_uploaded(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    Handle meeting-uploaded events.

    Triggered when external systems such as Feishu send meeting content
    through the EventBus.
    """
    payload = event.payload
    content = payload.get("content")
    source = payload.get("source", "event")
    title = payload.get("title")
    meeting_date = payload.get("meeting_date")
    participants = payload.get("participants", [])

    if not content:
        logger.warning("meeting_uploaded_missing_content", event_id=event.event_id)
        return []

    logger.info(
        "meeting_uploaded_received",
        event_id=event.event_id,
        title_hash=hash_identifier(title),
        title_length=len(str(title or "")),
        content_length=len(content),
    )

    try:
        # Process meeting content through the agent.
        async with agent._db_manager.session() as session:
            result = await agent.ingest_meeting(
                content=content,
                source=source,
                session=session,
                title=title,
                meeting_date=meeting_date,
                participants=participants
            )

        logger.info(
            "meeting_processed_from_event",
            event_id=event.event_id,
            requirements_count=result.requirements_extracted,
            questions_count=result.questions_generated
        )

    except Exception as e:
        logger.error(
            "meeting_processing_failed",
            event_id=event.event_id,
            error=str(e)
        )

    return []  # Events have already been published by ingest_meeting.
