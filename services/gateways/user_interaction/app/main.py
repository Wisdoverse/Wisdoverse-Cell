"""User interaction gateway FastAPI entry point."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.integrations.feishu.cards.tools import FeishuToolCardRenderer
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

from ..api.bitable import router as bitable_router
from ..api.daily_progress import router as daily_progress_router
from ..api.webhook import router as webhook_router
from ..core.card_ports import configure_tool_card_renderer
from ..core.ops_logger import configure_operation_log_store
from ..core.scheduler_use_cases import UserInteractionSchedulerUseCase
from ..db.database import db_manager
from ..db.operation_log_store import SqlAlchemyCardOperationLogStore
from ..service.agent import agent as _raw_agent
from .plugins import UserInteractionOutboxDispatcherPlugin

logger = get_logger("chat_agent.app")

scheduler = AsyncIOScheduler()
configure_tool_card_renderer(FeishuToolCardRenderer())
configure_operation_log_store(SqlAlchemyCardOperationLogStore(db_manager))

app = create_agent_app(
    _raw_agent,
    title="Chat Agent",
    description="User interaction gateway for chat, Feishu webhooks, and tool calling.",
    routers=[
        webhook_router,  # No auth (webhook endpoint)
        (bitable_router, [Depends(verify_internal_key)]),
        (daily_progress_router, [Depends(verify_internal_key)]),
    ],
    plugins=[
        InfraHealthPlugin(db_manager=db_manager),
        UserInteractionOutboxDispatcherPlugin(),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
    on_startup=lambda rt: _start_scheduler(rt),
    on_shutdown=lambda rt: _stop_scheduler(rt),
)


def _get_agent() -> BaseAgent:
    """Get the runtime-wrapped agent with startup guard."""
    runtime = getattr(app.state, "runtime", None)
    if runtime is None or not runtime.is_started:
        raise RuntimeError(
            "Agent runtime not initialized; scheduler fired before startup completed"
        )
    return runtime.agent


def get_scheduler_use_case() -> UserInteractionSchedulerUseCase:
    return UserInteractionSchedulerUseCase(_get_agent())


async def _run_scheduled_action(action: str) -> None:
    """Execute a scheduled agent action with logging and error handling."""
    logger.info("scheduled_action_triggered", action=action)
    try:
        await get_scheduler_use_case().run_scheduled_action(action)
    except Exception as e:
        logger.error(
            "scheduled_action_failed",
            action=action,
            error=str(e),
            error_type=type(e).__name__,
        )


async def _start_scheduler(runtime) -> None:
    scheduler.add_job(
        lambda: _run_scheduled_action("cleanup_conversations"),
        IntervalTrigger(hours=24),
        id="conversation_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_scheduled_action("dispatch_morning_tasks"),
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="Asia/Shanghai"),
        id="morning_task_dispatch",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_scheduled_action("collect_evening_progress"),
        CronTrigger(hour=17, minute=30, day_of_week="mon-fri", timezone="Asia/Shanghai"),
        id="evening_progress_collect",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("chat_agent_ready")


async def _stop_scheduler(runtime) -> None:
    scheduler.shutdown(wait=False)
