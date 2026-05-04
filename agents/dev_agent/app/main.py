"""FastAPI entry point for dev_agent."""

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends
from sqlalchemy import text

from shared.app import create_agent_app
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

from ..adapters.agentforge_client import ForgeClient
from ..adapters.gitlab_client import GitLabClient
from ..api.dev import router as dev_router
from ..core.security_scanner import SecurityScanner
from ..core.workflow_planner import inject_project_id
from ..db.database import db_manager
from ..db.repository import DevTaskRepository, DevWorkflowLogRepository
from ..service.agent import DevAgent
from ..service.config_factory import build_dev_core_config
from ..service.notifier_factory import build_dev_notifier

logger = get_logger("dev_agent.app")

_raw_agent = DevAgent()
scheduler = AsyncIOScheduler()

# Module-level references for lifecycle management
_forge_client: ForgeClient | None = None
_gitlab_client: GitLabClient | None = None

app = create_agent_app(
    _raw_agent,
    title="Dev Agent",
    description="Development execution agent for PJM-to-AgentForge delivery workflows.",
    routers=[
        (dev_router, [Depends(verify_internal_key)]),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
    on_startup=lambda rt: _on_startup(rt),
    on_shutdown=lambda rt: _on_shutdown(rt),
)


def _get_agent() -> BaseAgent:
    """Get the runtime-wrapped agent. Scheduler jobs call this to go through EvolvedAgent."""
    runtime = getattr(app.state, "runtime", None)
    if runtime is None or not runtime.is_started:
        raise RuntimeError(
            "Agent runtime not initialized; scheduler fired before startup completed"
        )
    return runtime.agent


async def _on_startup(runtime) -> None:
    """Initialize DB, services, and wire them into the agent."""
    global _forge_client, _gitlab_client

    # Development can create local tables; shared environments use Alembic.
    if settings.app_env == "development":
        await db_manager.create_tables()
        logger.info("dev_agent_db_initialized")
    else:
        logger.info("schema_managed_by_alembic", agent_id="dev-agent")

    # Create ForgeClient
    if settings.agentforge_api_url:
        _forge_client = ForgeClient(
            base_url=settings.agentforge_api_url,
            token=settings.agentforge_token.get_secret_value(),
        )

    # Create GitLabClient
    if settings.dev_gitlab_api_url and settings.dev_gitlab_project_id:
        _gitlab_client = GitLabClient(
            base_url=settings.dev_gitlab_api_url,
            token=settings.dev_gitlab_token.get_secret_value(),
            project_id=settings.dev_gitlab_project_id,
        )

    # Wire dependencies into the raw agent
    # ForgeClient is set via the agent's own startup(); also store module ref
    _raw_agent._forge = _forge_client

    # Create session-independent repos will be created per-session in reconcile,
    # but for the agent's handle_event we need a session factory approach.
    # Wire the db_manager so agent can create sessions on demand.
    _raw_agent._db_manager = db_manager

    # Create notifier and security scanner
    notifier = build_dev_notifier()
    scanner = SecurityScanner()

    # Create ResultCollector (will use per-session repos)
    if _gitlab_client:
        _raw_agent._gitlab_client = _gitlab_client
        _raw_agent._notifier = notifier
        _raw_agent._scanner = scanner

    logger.info("dev_agent_services_wired")

    # Start scheduler
    await _start_scheduler(runtime)


async def _on_shutdown(runtime) -> None:
    """Clean up resources."""
    global _forge_client, _gitlab_client

    await _stop_scheduler(runtime)

    if _forge_client:
        await _forge_client.close()
        _forge_client = None
    if _gitlab_client:
        await _gitlab_client.close()
        _gitlab_client = None

    logger.info("dev_agent_shutdown_complete")


async def _start_scheduler(runtime) -> None:
    scheduler.add_job(
        _reconcile,
        IntervalTrigger(seconds=30),
        id="reconciliation_loop",
        replace_existing=True,
    )
    scheduler.add_job(
        _expire_stale,
        IntervalTrigger(hours=1),
        id="expire_stale_pending",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("dev_scheduler_started")


async def _stop_scheduler(runtime) -> None:
    scheduler.shutdown(wait=False)
    logger.info("dev_scheduler_stopped")


def _poll_interval(elapsed: timedelta) -> timedelta | None:
    """Return the minimum polling interval for a given elapsed time, or None if timed out."""
    if elapsed < timedelta(minutes=10):
        return timedelta(seconds=30)
    if elapsed < timedelta(hours=2):
        return timedelta(minutes=2)
    if elapsed < timedelta(hours=6):
        return timedelta(minutes=5)
    return None  # Timed out


async def _reconcile() -> None:
    """ReconciliationLoop: scan active tasks, poll AgentForge, trigger result collection,
    and start pending/planning tasks when slots open."""
    try:
        agent = _get_agent()
    except RuntimeError:
        return  # Not started yet

    from ..app.metrics import ACTIVE_WORKFLOWS, FORGE_POLL_ERRORS, PENDING_TASKS
    from ..core.result_collector import ResultCollector
    from ..core.security_scanner import SecurityScanner

    try:
        async with db_manager.session() as session:
            # Advisory lock: ensure single-instance reconciliation
            lock_result = await session.execute(
                text("SELECT pg_try_advisory_lock(hashtext('dev_agent_reconcile'))")
            )
            if not lock_result.scalar():
                logger.debug("reconcile_lock_not_acquired")
                return

            try:
                repo = DevTaskRepository(session)
                log_repo = DevWorkflowLogRepository(session)

                # Update gauge metrics
                active_tasks = await repo.list_active_tasks()
                pending_tasks = await repo.list_pending_tasks(limit=100)
                ACTIVE_WORKFLOWS.set(len(active_tasks))
                PENDING_TASKS.set(len(pending_tasks))

                now = datetime.now(UTC)
                for task in active_tasks:
                    if not task.workflow_id or not task.workflow_started_at:
                        # Task in post-execution states (security_scanning etc.)
                        # without workflow_id — skip polling, handled by result_collector
                        continue

                    # Only poll tasks in 'executing' status
                    if task.status != "executing":
                        continue

                    elapsed = now - task.workflow_started_at
                    min_interval = _poll_interval(elapsed)

                    if min_interval is None:
                        await repo.update_status(
                            task.id,
                            "failed",
                            error_message="Workflow execution timed out (>6h)",
                            failed_step="timeout",
                        )
                        logger.warning(
                            "workflow_timeout",
                            wp_id=task.wp_id,
                            task_id=task.id,
                        )
                        continue

                    last_poll = task.last_polled_at or task.workflow_started_at
                    if (now - last_poll) < min_interval:
                        continue

                    logger.debug(
                        "polling_workflow",
                        task_id=task.id,
                        workflow_id=task.workflow_id,
                    )
                    task.last_polled_at = now
                    task.updated_at = now
                    await session.flush()

                    # Poll AgentForge using the module-level forge client
                    try:
                        if _forge_client and task.workflow_id:
                            status = await _forge_client.get_status(task.workflow_id)
                            workflow = status.get("workflow", {})
                            wf_status = workflow.get("status") or status.get("status", "")
                            if wf_status in ("completed", "finished", "done"):
                                logger.info(
                                    "workflow_completed",
                                    task_id=task.id,
                                    workflow_id=task.workflow_id,
                                )
                                # Trigger result collection pipeline
                                if _gitlab_client:
                                    core_config = (
                                        getattr(agent, "_core_config", None)
                                        or build_dev_core_config()
                                    )
                                    collector = ResultCollector(
                                        repo=repo,
                                        log_repo=log_repo,
                                        gitlab=_gitlab_client,
                                        notifier=getattr(agent, "_notifier", None)
                                        or build_dev_notifier(),
                                        security_scanner=getattr(agent, "_scanner", None)
                                        or SecurityScanner(),
                                        config=core_config,
                                    )
                                    events = await collector.handle_completion(task, status)
                                    # Publish events returned by ResultCollector
                                    # (qa.run-requested, dev.mr-created, etc.)
                                    if events:
                                        from shared.infra.event_bus import event_bus
                                        for evt in events:
                                            try:
                                                await event_bus.publish(evt)
                                            except Exception as pub_err:
                                                logger.error(
                                                    "event_publish_error",
                                                    event_type=evt.event_type,
                                                    error=str(pub_err),
                                                    exc_info=True,
                                                )
                                else:
                                    # No GitLab client — just mark security_scanning
                                    await repo.update_status(task.id, "security_scanning")
                                    logger.warning(
                                        "gitlab_not_configured",
                                        task_id=task.id,
                                        msg="Cannot run result collection pipeline",
                                    )
                    except Exception as poll_err:
                        logger.error(
                            "poll_workflow_error",
                            task_id=task.id,
                            error=str(poll_err),
                            exc_info=True,
                        )
                        FORGE_POLL_ERRORS.inc()

                # C3: Start pending tasks when slots open
                active_count = await repo.count_active_workflows()
                if active_count < settings.dev_max_concurrent_workflows:
                    slots = settings.dev_max_concurrent_workflows - active_count
                    pending = await repo.list_pending_tasks(limit=slots)
                    for task in pending:
                        try:
                            await _start_pending_task(task, repo, log_repo)
                        except Exception as e:
                            logger.error(
                                "pending_task_start_error",
                                task_id=task.id,
                                error=str(e),
                                exc_info=True,
                            )

                # C4: Re-enter pipeline for planning tasks (QA retry re-entry)
                active_count = await repo.count_active_workflows()
                if active_count < settings.dev_max_concurrent_workflows:
                    slots = settings.dev_max_concurrent_workflows - active_count
                    planning = await repo.list_planning_tasks(limit=slots)
                    for task in planning:
                        # Only re-enter if this is a retry (retry_count > 0)
                        if task.retry_count > 0:
                            try:
                                await _start_pending_task(task, repo, log_repo)
                            except Exception as e:
                                logger.error(
                                    "planning_retry_error",
                                    task_id=task.id,
                                    error=str(e),
                                    exc_info=True,
                                )

                await session.commit()
            finally:
                await session.execute(
                    text(
                        "SELECT pg_advisory_unlock(hashtext('dev_agent_reconcile'))"
                    )
                )
    except Exception as e:
        FORGE_POLL_ERRORS.inc()
        logger.error("reconcile_error", error=str(e), exc_info=True)


async def _start_pending_task(task, repo, log_repo) -> None:
    """Start a pending/planning task through the plan-and-execute pipeline."""
    from ..models.schemas import RiskLevel, SanitizedTask

    agent = _get_agent()

    # Try to restore full task context from workflow log
    wf_log = await log_repo.get_by_task_id(task.id)
    task_input_data = None
    if wf_log and wf_log.workflow_json and "task_input" in wf_log.workflow_json:
        task_input_data = wf_log.workflow_json["task_input"]

    if task_input_data:
        sanitized = SanitizedTask.model_validate(task_input_data)
    else:
        sanitized = SanitizedTask(
            title=task.task_title or "",
            description="",
            estimated_hours=8,
            wp_id=task.wp_id,
            risk_level=RiskLevel(task.risk_level) if task.risk_level else RiskLevel.MEDIUM,
        )
    risk = sanitized.risk_level

    # Use the agent's planner/validator/router
    await repo.update_status(task.id, "planning")
    plan = await agent._planner.plan(sanitized)
    if plan is None:
        await repo.update_status(
            task.id, "failed", error_message="Workflow planning failed (reconcile)"
        )
        return

    plan = inject_project_id(plan, settings.dev_agentforge_project_id)
    validation = agent._validator.validate(plan)
    if not validation.is_valid:
        await repo.update_status(
            task.id, "failed",
            error_message=f"Validation: {'; '.join(validation.violations)}",
        )
        return

    for node in plan.nodes:
        tool = agent._router.route(node)
        node.config["cliTool"] = tool

    plan_json = plan.model_dump()
    if risk == RiskLevel.HIGH:
        approval_id = await agent._request_workflow_approval(
            sanitized=sanitized,
            task_id=task.id,
            plan_json=plan_json,
        )
        if approval_id:
            plan_json["control_plane_approval_id"] = approval_id

    # Store workflow plan
    await log_repo.create_log(task_id=task.id, workflow_json=plan_json)

    if risk == RiskLevel.HIGH:
        await repo.update_status(task.id, "awaiting_approval")
        return

    if _forge_client:
        workflow_id = await _forge_client.create_workflow(plan)
        await _forge_client.run_workflow(workflow_id)
        await repo.update_status(
            task.id,
            "executing",
            workflow_id=workflow_id,
            workflow_started_at=datetime.now(UTC),
        )
        logger.info("pending_task_started", task_id=task.id, workflow_id=workflow_id)
    else:
        logger.warning("forge_not_available", task_id=task.id)


async def _expire_stale() -> None:
    """Expire pending tasks older than 24 hours."""
    try:
        _get_agent()
    except RuntimeError:
        return

    try:
        from ..db.database import db_manager
        from ..db.repository import DevTaskRepository

        async with db_manager.session() as session:
            repo = DevTaskRepository(session)
            expired = await repo.expire_stale_pending(hours=24)
            if expired > 0:
                logger.info("expired_stale_tasks", count=expired)
            await session.commit()
    except Exception as e:
        logger.error("expire_stale_error", error=str(e), exc_info=True)
