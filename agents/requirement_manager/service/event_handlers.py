"""
Event Handlers - 事件处理器

按事件类型分发处理逻辑。
当 Agent 订阅事件后，接收到的事件通过此模块路由到对应的处理函数。
"""
from typing import TYPE_CHECKING

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from .agent import RequirementManagerAgent

logger = get_logger("requirement-manager.event_handlers")


# 订阅的事件类型
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
    事件分发器

    根据事件类型路由到对应的处理函数。

    Args:
        agent: Agent 实例
        event: 接收到的事件

    Returns:
        处理过程中产生的新事件列表
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


# ========== 事件处理函数 ==========

async def handle_project_created(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    处理项目创建事件

    当新项目创建时，自动关联待确认的相关需求。
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

    # 查找可能相关的需求 (基于关键词)
    # 未来可以实现自动关联逻辑
    # async with agent._db_manager.session() as session:
    #     repo = RequirementRepository(session)
    #     # 搜索包含项目关键词的需求
    #     # 自动添加项目标签

    return []


async def handle_project_updated(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    处理项目更新事件

    当项目信息更新时，可能需要更新关联需求的状态。
    """
    payload = event.payload
    project_id = payload.get("project_id")
    changes = payload.get("changes", {})

    logger.info(
        "project_updated_received",
        project_id=project_id,
        changes=list(changes.keys())
    )

    # 未来实现：根据项目状态变化更新需求
    return []


async def handle_sprint_started(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    处理迭代开始事件

    当新迭代开始时:
    1. 高亮当前迭代相关的需求
    2. 发送提醒到飞书群
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

    # 未来实现:
    # 1. 标记需求为"本迭代"
    # 2. 发送飞书通知

    return []


async def handle_sprint_completed(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    处理迭代完成事件

    当迭代完成时:
    1. 统计需求完成情况
    2. 生成迭代报告
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

    # 未来实现:
    # 1. 生成迭代总结
    # 2. 将未完成需求标记为下迭代

    return []


async def handle_meeting_uploaded(
    agent: "RequirementManagerAgent",
    event: Event
) -> list[Event]:
    """
    处理会议上传事件

    当外部系统（如飞书）通过事件总线发送会议内容时触发。
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
        title=title,
        content_length=len(content)
    )

    try:
        # 通过 Agent 处理会议内容
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

    return []  # 事件已在 ingest_meeting 中发布
