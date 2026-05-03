"""User interaction gateway service for chat and Feishu webhook requests."""
from typing import Optional

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.chat_service import ChatService
from ..core.daily_tasks import (
    DailyTaskDependencies,
    configure_daily_task_dependencies,
)
from ..core.tools import ToolDependencies, configure_tool_dependencies
from ..db.database import DatabaseManager, db_manager

logger = get_logger("chat_agent.service")


class ChatAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
    ):
        super().__init__(
            agent_id="chat-agent",
            agent_name="聊天Agent",
            subscribed_events=[
                EventTypes.CHAT_PM_RESPONSE,
                EventTypes.COORDINATOR_RESPONSE,
            ],
            published_events=[
                EventTypes.CHAT_PM_QUERY,
                EventTypes.COORDINATOR_COMMAND,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._chat: ChatService | None = None

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        feishu_client = get_feishu_client()
        configure_tool_dependencies(
            ToolDependencies(
                op_client=get_op_client(),
                bitable=bitable_service,
                messenger=feishu_client,
                contact_lookup=feishu_client,
            )
        )
        configure_daily_task_dependencies(
            DailyTaskDependencies(
                bitable=bitable_service,
                messenger=feishu_client,
            )
        )
        self._chat = ChatService()

        # Event loop is managed by AgentRuntime.start_event_loop()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.CHAT_PM_RESPONSE:
            logger.info("project_management_response_received", user_id=event.payload.get("user_id"))
        elif event.event_type == EventTypes.COORDINATOR_RESPONSE:
            logger.info(
                "coordinator_response_received",
                task_id=event.payload.get("task_id"),
                workflow_id=event.payload.get("workflow_id"),
            )
        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "chat":
            message = request.get("message", "")
            user_id = request.get("user_id", "anonymous")
            reply = await self._chat.chat(message=message, user_id=user_id)
            return {"reply": reply}
        if action == "chat_user_assistant":
            message = request.get("message", "")
            user_id = request.get("user_id", "anonymous")
            user_name = request.get("user_name", "")
            context = {
                "user_id": user_id,
                "user_name": user_name,
                "chat_id": request.get("chat_id", ""),
                "chat_type": request.get("chat_type", "p2p"),
            }
            reply = await self._chat.chat_with_user_assistant(
                message=message, user_id=user_id, user_name=user_name, context=context,
            )
            return {"reply": reply}
        if action == "clear_history":
            user_id = request.get("user_id", "")
            await self._chat.clear_history(user_id)
            return {"status": "cleared"}
        if action == "cleanup_conversations":
            return await self._cleanup_conversations()
        if action == "dispatch_morning_tasks":
            from ..core.daily_tasks import dispatch_morning_tasks
            await dispatch_morning_tasks()
            return {"status": "ok"}
        if action == "collect_evening_progress":
            from ..core.daily_tasks import collect_evening_progress
            await collect_evening_progress()
            return {"status": "ok"}
        return {"error": "unknown action"}

    async def _cleanup_conversations(self) -> dict:
        from ..db.repository import ConversationRepository
        async with self._db_manager.session() as session:
            repo = ConversationRepository(session)
            deleted = await repo.delete_inactive(days=30)
            await session.commit()
        logger.info("conversation_cleanup_done", deleted=deleted)
        return {"status": "ok", "deleted": deleted}

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        checks = {"database": False}
        try:
            if self._db_manager:
                from sqlalchemy import text
                async with self._db_manager.session() as session:
                    await session.execute(text("SELECT 1"))
                checks["database"] = True
        except Exception as e:
            logger.error("health_check_db_failed", error=str(e), error_type=type(e).__name__)
        checks["chat_service"] = self._chat is not None
        return checks


agent = ChatAgent()


def get_agent() -> ChatAgent:
    return agent
