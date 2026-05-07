"""SyncModule FastAPI entrypoint.

The scheduler keeps the legacy full-sync behavior. Operators can trigger the
OpenProject and Feishu Bitable sync boundaries independently through API
routes when only one side needs reconciliation.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

from ..api.sync import router as sync_router
from ..service.agent import agent as _raw_agent

logger = get_logger("sync_module.app")

scheduler = AsyncIOScheduler()

app = create_agent_app(
    _raw_agent,
    title="Sync Module",
    description="OpenProject and Feishu Bitable sync support capability",
    routers=[(sync_router, [Depends(verify_internal_key)])],
    plugins=[InfraHealthPlugin()],
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
            "Agent runtime not initialized; "
            "scheduler fired before startup completed"
        )
    return runtime.agent


async def _scheduled_sync() -> None:
    logger.info("scheduled_sync_triggered")
    try:
        await _get_agent().trigger_sync(triggered_by="scheduler")
    except Exception as e:
        logger.error("scheduled_sync_failed", error=str(e), error_type=type(e).__name__)


async def _start_scheduler(runtime) -> None:
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger(hour=18, minute=0, timezone="Asia/Shanghai"),
        id="daily_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("sync_scheduler_started", schedule="daily 18:00")


async def _stop_scheduler(runtime) -> None:
    scheduler.shutdown(wait=False)
