"""PMAgent FastAPI 入口"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

from ..api.decomposition import router as decomposition_router
from ..api.pm import router as pm_router
from ..service.agent import agent as _raw_agent

# Backward-compatible alias: test_api.py patches `agents.capabilities.project_management.app.main.agent`
agent = _raw_agent

logger = get_logger("pjm_agent.app")

try:
    from .metrics import ALERTS_TRIGGERED

    _prometheus_available = True
except ImportError:
    _prometheus_available = False

scheduler = AsyncIOScheduler()

app = create_agent_app(
    _raw_agent,
    title="PJM Agent",
    description="PJM 预警调度 Agent",
    routers=[
        (pm_router, [Depends(verify_internal_key)]),
        (decomposition_router, [Depends(verify_internal_key)]),
    ],
    plugins=[InfraHealthPlugin()],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
    on_startup=lambda rt: _start_scheduler(rt),
    on_shutdown=lambda rt: _stop_scheduler(rt),
)


def _get_agent() -> BaseAgent:
    """Get the runtime-wrapped agent. Scheduler jobs call this to go through EvolvedAgent."""
    runtime = getattr(app.state, "runtime", None)
    if runtime is None or not runtime._started:
        raise RuntimeError(
            "Agent runtime not initialized; scheduler fired before startup completed"
        )
    return runtime.agent


async def _start_scheduler(runtime) -> None:
    scheduler.add_job(
        _hourly_alerts, IntervalTrigger(days=2), id="periodic_alerts", replace_existing=True
    )
    scheduler.add_job(
        _refresh_config, IntervalTrigger(minutes=5), id="refresh_config", replace_existing=True
    )
    scheduler.add_job(
        _daily_report,
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="Asia/Shanghai"),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.add_job(
        _weekly_report,
        CronTrigger(hour=20, minute=0, day_of_week="thu", timezone="Asia/Shanghai"),
        id="weekly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        _check_stale_approvals,
        IntervalTrigger(hours=6),
        id="stale_approvals_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("pm_scheduler_started")


async def _stop_scheduler(runtime) -> None:
    scheduler.shutdown(wait=False)


async def _hourly_alerts() -> None:
    logger.info("hourly_alerts_triggered")
    try:
        agent = _get_agent()
        result = await agent.handle_request({"action": "alerts"})
        alerts = result.get("alerts", [])
        if alerts:
            await agent.handle_request({"action": "push_alerts", "alerts": alerts})
            if _prometheus_available:
                for a in alerts:
                    ALERTS_TRIGGERED.labels(
                        alert_type=a.get("type", "unknown"),
                        severity=a.get("severity", "unknown"),
                    ).inc()
    except Exception as e:
        logger.error("hourly_alerts_failed", error=str(e), error_type=type(e).__name__)


async def _run_scheduled_action(action: str) -> None:
    """Execute a scheduled agent action with logging and error handling."""
    logger.info("scheduled_action_triggered", action=action)
    try:
        await _get_agent().handle_request({"action": action})
    except Exception as e:
        logger.error(
            "scheduled_action_failed", action=action, error=str(e), error_type=type(e).__name__
        )


async def _refresh_config() -> None:
    await _run_scheduled_action("refresh_config")


async def _daily_report() -> None:
    await _run_scheduled_action("daily_report")


async def _weekly_report() -> None:
    await _run_scheduled_action("weekly_report")


async def _check_stale_approvals() -> None:
    await _run_scheduled_action("check_stale_approvals")
