"""DevAgent — Thin Orchestrator for PJM -> AgentForge -> QA workflow."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from shared.config import settings
from shared.control_plane import (
    ApprovalCategory,
    ApprovalGateService,
    ApprovalRequiredError,
)
from shared.infra.llm_gateway import LLMGateway
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..adapters.agentforge_client import ForgeClient, ForgeClientError
from ..app.metrics import (
    TASKS_FAILED,
    WORKFLOWS_CREATED,
)
from ..core.input_sanitizer import InputRejectedError, InputSanitizer
from ..core.notifier import DevNotifier
from ..core.result_collector import ResultCollector
from ..core.risk_assessor import TaskRiskAssessor
from ..core.security_scanner import SecurityScanner
from ..core.tool_router import ToolRouter
from ..core.workflow_planner import WorkflowPlanner, inject_project_id
from ..core.workflow_validator import WorkflowValidator
from ..db.repository import DevTaskRepository, DevWorkflowLogRepository
from ..models.schemas import RiskLevel, SanitizedTask, TaskInput
from .notifier_factory import build_dev_notifier

if TYPE_CHECKING:
    from ..adapters.gitlab_client import GitLabClient
    from ..db.database import DatabaseManager

logger = get_logger("dev_agent.service")


class DevAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="dev-agent",
            agent_name="Dev Agent",
            subscribed_events=[
                EventTypes.PM_TASKS_READY_FOR_DEV,
                EventTypes.QA_ACCEPTANCE_COMPLETED,
            ],
            published_events=[
                EventTypes.DEV_WORKFLOW_CREATED,
                EventTypes.DEV_MR_CREATED,
                EventTypes.DEV_TASK_COMPLETED,
                EventTypes.DEV_TASK_FAILED,
                EventTypes.QA_RUN_REQUESTED,
            ],
        )
        self._sanitizer = InputSanitizer()
        self._risk_assessor = TaskRiskAssessor()
        self._validator = WorkflowValidator()
        self._router = ToolRouter()
        self._planner = WorkflowPlanner(LLMGateway())

        self._forge: ForgeClient | None = None
        self._db_manager: DatabaseManager | None = None
        self._gitlab_client: GitLabClient | None = None
        self._notifier: DevNotifier | None = None
        self._scanner: SecurityScanner | None = None

        # Legacy per-session repos (kept for backward compat in tests)
        self._repo: DevTaskRepository | None = None
        self._log_repo: DevWorkflowLogRepository | None = None
        self._result_collector: ResultCollector | None = None
        self._approval_gate = ApprovalGateService(source_agent_id=self.agent_id)

    async def startup(self) -> None:
        logger.info("dev_agent_starting")
        # ForgeClient is now wired by app/main.py _on_startup
        # Keep this for backward compat if startup is called directly
        if not self._forge:
            token = settings.agentforge_token.get_secret_value()
            if settings.agentforge_api_url:
                self._forge = ForgeClient(
                    base_url=settings.agentforge_api_url,
                    token=token,
                )
        if self._notifier is None:
            self._notifier = build_dev_notifier()

    async def shutdown(self) -> None:
        logger.info("dev_agent_shutting_down")
        # ForgeClient lifecycle now managed by app/main.py _on_shutdown

    def set_repository(self, repo: DevTaskRepository) -> None:
        """Inject repository after DB session is available."""
        self._repo = repo

    def set_log_repository(self, log_repo: DevWorkflowLogRepository) -> None:
        """Inject workflow log repository after DB session is available."""
        self._log_repo = log_repo

    def set_result_collector(self, collector: ResultCollector) -> None:
        """Inject result collector after dependencies are available."""
        self._result_collector = collector

    def _has_db(self) -> bool:
        """Check if database is available (either db_manager or injected repo)."""
        return self._db_manager is not None or self._repo is not None

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV:
            return await self._handle_tasks_ready(event)
        if event.event_type == EventTypes.QA_ACCEPTANCE_COMPLETED:
            return await self._handle_qa_result(event)
        return []

    async def handle_request(self, request: dict) -> dict:
        standard = await self.handle_standard_request(request)
        if standard is not None:
            return standard
        action = request.get("action")

        if not self._has_db():
            if action in ("list_active_workflows", "list_failed"):
                return {"workflows": []}
            return {"error": "Database not initialized"}

        async with self._get_session() as session:
            repo = self._get_repo(session)
            result = await self._dispatch_action(action, request, repo, session)
            await session.commit()
            return result

    async def _dispatch_action(
        self, action: str | None, request: dict, repo: DevTaskRepository, session
    ) -> dict:
        if action == "get_task_status":
            wp_id = request.get("wp_id")
            if not wp_id:
                return {"error": "wp_id required"}
            task = await repo.get_by_wp_id(wp_id)
            if not task:
                return {"error": f"Task not found for wp_id={wp_id}"}
            return {
                "wp_id": task.wp_id,
                "status": task.status,
                "risk_level": task.risk_level,
                "workflow_id": task.workflow_id,
                "mr_url": task.mr_url,
                "retry_count": task.retry_count,
                "error_message": task.error_message,
                "created_at": str(task.created_at) if task.created_at else None,
            }

        if action == "list_active_workflows":
            tasks = await repo.list_active_tasks()
            return {
                "workflows": [
                    {
                        "wp_id": t.wp_id,
                        "status": t.status,
                        "workflow_id": t.workflow_id,
                        "risk_level": t.risk_level,
                    }
                    for t in tasks
                ]
            }

        if action == "list_failed":
            tasks = await repo.list_failed_tasks()
            return {
                "workflows": [
                    {
                        "wp_id": t.wp_id,
                        "status": t.status,
                        "error_message": t.error_message,
                        "failed_step": t.failed_step,
                        "retry_count": t.retry_count,
                    }
                    for t in tasks
                ]
            }

        if action == "retry_task":
            task_id = request.get("task_id")
            if not task_id:
                return {"error": "task_id required"}
            task = await repo.get_by_id(task_id)
            if not task or task.status != "failed":
                return {"error": "Task not found or not in failed state"}
            success = await repo.update_status(
                task_id, "planning", retry_count=task.retry_count + 1
            )
            return {"success": success, "task_id": task_id}

        if action == "cancel_workflow":
            task_id = request.get("task_id")
            if not task_id:
                return {"error": "task_id required"}
            success = await repo.update_status(
                task_id, "failed", error_message="Manually cancelled"
            )
            return {"success": success}

        if action == "approve_workflow":
            task_id = request.get("task_id")
            if not task_id:
                return {"error": "task_id required"}
            task = await repo.get_by_id(task_id)
            if not task or task.status != "awaiting_approval":
                return {"error": "Task not found or not awaiting approval"}

            # Retrieve stored workflow plan and execute it
            log_repo = DevWorkflowLogRepository(session)
            wf_log = await log_repo.get_by_task_id(task_id)
            if wf_log and wf_log.workflow_json:
                approval_id = request.get("approval_id") or wf_log.workflow_json.get(
                    "control_plane_approval_id"
                )
                approved_by = request.get("approved_by") or request.get("operator") or "api"
                try:
                    approval_decision = await self._approval_gate.approve_for_sensitive_action(
                        approval_id,
                        resolved_by=approved_by,
                    )
                except ApprovalRequiredError as exc:
                    logger.warning(
                        "approve_workflow_control_plane_required",
                        task_id=task_id,
                        approval_id=approval_id,
                        error=str(exc),
                    )
                    return {"error": str(exc), "task_id": task_id}

                from ..models.schemas import WorkflowPlan
                plan = WorkflowPlan.model_validate(wf_log.workflow_json)
                exec_events = await self._execute_workflow(plan, task, repo)
                if exec_events:
                    return {
                        "success": True,
                        "task_id": task_id,
                        "workflow_started": True,
                        "control_plane_approval_id": (
                            approval_decision.approval_id if approval_decision else approval_id
                        ),
                    }
                return {
                    "success": True,
                    "task_id": task_id,
                    "workflow_started": False,
                    "control_plane_approval_id": (
                        approval_decision.approval_id if approval_decision else approval_id
                    ),
                }
            else:
                # No stored plan — cannot proceed without a workflow plan
                logger.error(
                    "approve_missing_workflow_plan",
                    task_id=task_id,
                    msg="Cannot execute: workflow plan not found in logs",
                )
                return {
                    "error": "Workflow plan not found — cannot execute without a plan",
                    "task_id": task_id,
                }

        return {"error": f"Unknown action: {action}"}

    async def _handle_tasks_ready(self, event: Event) -> list[Event]:
        payload = event.payload
        if payload.get("instruction"):
            logger.info(
                "coordinator_instruction_received",
                instruction=payload.get("instruction"),
                workflow_id=payload.get("workflow_id"),
            )
        wp_id = payload.get("wp_id")
        tasks = payload.get("tasks", [])
        events: list[Event] = []

        # Pre-process: sanitize and risk-assess all tasks first.
        # CRITICAL tasks are rejected immediately (no DB needed).
        sanitized_tasks: list[tuple[TaskInput, SanitizedTask, RiskLevel]] = []
        for task_data in tasks:
            try:
                task_input = TaskInput(
                    title=task_data.get("title", ""),
                    description=task_data.get("description", ""),
                    estimated_hours=task_data.get("estimated_hours", 8),
                    wp_id=task_data.get("id", wp_id),
                    parent_story=task_data.get("parent_story", ""),
                    related_files=task_data.get("related_files", []),
                )
                sanitized = self._sanitizer.sanitize(task_input)
                risk = self._risk_assessor.assess(sanitized)
                sanitized.risk_level = risk

                if risk == RiskLevel.CRITICAL:
                    logger.warning("task_rejected_critical", wp_id=sanitized.wp_id)
                    events.append(
                        Event.create(
                            event_type=EventTypes.DEV_TASK_FAILED,
                            source_agent="dev-agent",
                            payload={
                                "wp_id": sanitized.wp_id,
                                "error": "CRITICAL risk - requires human implementation",
                                "failed_node": "",
                                "runbook_url": "",
                            },
                        )
                    )
                    continue

                sanitized_tasks.append((task_input, sanitized, risk))

            except InputRejectedError as e:
                logger.warning(
                    "task_input_rejected", wp_id=wp_id, reasons=e.reasons
                )
            except Exception as e:
                logger.error(
                    "task_processing_error",
                    wp_id=wp_id,
                    error=str(e),
                    exc_info=True,
                )
                events.append(
                    Event.create(
                        event_type=EventTypes.DEV_TASK_FAILED,
                        source_agent="dev-agent",
                        payload={
                            "wp_id": wp_id,
                            "error": str(e),
                            "failed_node": "",
                            "runbook_url": "",
                        },
                    )
                )

        # Process non-CRITICAL tasks (requires DB)
        if not sanitized_tasks:
            return events

        if not self._has_db():
            logger.warning("db_not_available", msg="Cannot process tasks — no DB")
            return events

        async with self._get_session() as session:
            repo = self._get_repo(session)
            log_repo = DevWorkflowLogRepository(session)
            for _task_input, sanitized, risk in sanitized_tasks:
                try:
                    new_events = await self._process_single_task(
                        sanitized, risk, repo, log_repo
                    )
                    events.extend(new_events)
                except Exception as e:
                    logger.error(
                        "task_processing_error",
                        wp_id=sanitized.wp_id,
                        error=str(e),
                        exc_info=True,
                    )
            await session.commit()
        return events

    async def _process_single_task(
        self, sanitized: SanitizedTask, risk: RiskLevel,
        repo: DevTaskRepository, log_repo: DevWorkflowLogRepository,
    ) -> list[Event]:
        """Process a single already-sanitized task through plan -> execute pipeline."""
        events: list[Event] = []
        logger.info("task_accepted", wp_id=sanitized.wp_id, risk=risk.value)

        task_record = await repo.create_task(
            wp_id=sanitized.wp_id,
            task_title=sanitized.title,
            risk_level=risk.value,
        )
        if task_record is None:
            logger.info("task_already_exists", wp_id=sanitized.wp_id)
            return events

        # Persist full task input context for restore (pending/planning recovery)
        await log_repo.create_log(
            task_id=task_record.id,
            workflow_json={"task_input": sanitized.model_dump()},
        )

        active_count = await repo.count_active_workflows()
        if active_count >= settings.dev_max_concurrent_workflows:
            logger.info(
                "task_queued",
                wp_id=sanitized.wp_id,
                active=active_count,
            )
            return events

        new_events = await self._plan_and_execute(
            sanitized, task_record, repo, log_repo, risk
        )
        events.extend(new_events)
        return events

    async def _plan_and_execute(
        self, sanitized, task_record, repo, log_repo, risk
    ) -> list[Event]:
        """Plan workflow and execute (or queue for approval). Reusable for retries."""
        events: list[Event] = []

        await repo.update_status(task_record.id, "planning")
        plan = await self._planner.plan(sanitized)
        if plan is None:
            await repo.update_status(
                task_record.id,
                "failed",
                error_message="Workflow planning failed",
            )
            TASKS_FAILED.labels(reason="planning").inc()
            return events

        plan = inject_project_id(plan, settings.dev_agentforge_project_id)
        validation = self._validator.validate(plan)
        if not validation.is_valid:
            await repo.update_status(
                task_record.id,
                "failed",
                error_message=f"Validation: {'; '.join(validation.violations)}",
            )
            TASKS_FAILED.labels(reason="validation").inc()
            return events

        for node in plan.nodes:
            tool = self._router.route(node)
            node.config["cliTool"] = tool

        plan_json = plan.model_dump()
        if risk == RiskLevel.HIGH:
            approval_id = await self._request_workflow_approval(
                sanitized=sanitized,
                task_id=task_record.id,
                plan_json=plan_json,
            )
            if approval_id:
                plan_json["control_plane_approval_id"] = approval_id

        # Store workflow plan in workflow_logs for later retrieval (approval flow)
        await log_repo.create_log(
            task_id=task_record.id,
            workflow_json=plan_json,
        )

        if risk == RiskLevel.HIGH:
            await repo.update_status(
                task_record.id, "awaiting_approval"
            )
            logger.info(
                "task_awaiting_approval", wp_id=sanitized.wp_id
            )
            return events

        return await self._execute_workflow(plan, task_record, repo)

    async def _request_workflow_approval(
        self,
        *,
        sanitized: SanitizedTask,
        task_id: str,
        plan_json: dict,
    ) -> str | None:
        try:
            approval = await self._approval_gate.request_approval(
                category=ApprovalCategory.TECHNICAL,
                proposed_action=f"Start high-risk AgentForge workflow for WP#{sanitized.wp_id}",
                reason=sanitized.title,
                risk=(
                    "HIGH risk dev task will create and run an AgentForge workflow "
                    f"with {len(plan_json.get('nodes', []))} nodes."
                ),
                rollback_note=(
                    "Cancel or mark the dev task failed before external workflow execution."
                ),
                affected_resources=[
                    f"dev_task:{task_id}",
                    f"openproject:wp:{sanitized.wp_id}",
                    "agentforge:workflow",
                ],
            )
        except Exception as exc:
            logger.error(
                "workflow_approval_request_failed",
                task_id=task_id,
                wp_id=sanitized.wp_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._approval_gate.enforced:
                raise
            return None
        return approval.approval_id if approval is not None else None

    async def _execute_workflow(self, plan, task_record, repo) -> list[Event]:
        """Submit workflow to AgentForge and update status."""
        events: list[Event] = []
        if self._forge:
            try:
                plan = inject_project_id(plan, settings.dev_agentforge_project_id)
                workflow_id = await self._forge.create_workflow(plan)
                await self._forge.run_workflow(workflow_id)
                await repo.update_status(
                    task_record.id,
                    "executing",
                    workflow_id=workflow_id,
                    workflow_started_at=datetime.now(UTC),
                )
                WORKFLOWS_CREATED.inc()
                events.append(
                    Event.create(
                        event_type=EventTypes.DEV_WORKFLOW_CREATED,
                        source_agent="dev-agent",
                        payload={
                            "task_id": task_record.id,
                            "workflow_id": workflow_id,
                            "node_count": len(plan.nodes),
                        },
                    )
                )
            except ForgeClientError as e:
                logger.error(
                    "forge_client_error",
                    wp_id=task_record.wp_id,
                    error=str(e),
                    exc_info=True,
                )
                await repo.update_status(
                    task_record.id,
                    "failed",
                    error_message=str(e),
                )
                TASKS_FAILED.labels(reason="forge_error").inc()
        else:
            logger.warning(
                "forge_not_initialized",
                wp_id=task_record.wp_id,
                msg="Skipping execution — ForgeClient not available",
            )
        return events

    async def _handle_qa_result(self, event: Event) -> list[Event]:
        logger.info("qa_result_received", payload=event.payload)

        mr_iid = event.payload.get("mr_iid")
        if mr_iid is None:
            logger.warning("qa_result_missing_mr_iid")
            return []

        if not self._has_db():
            logger.warning("db_not_available", msg="Cannot process QA result")
            return []

        async with self._get_session() as session:
            repo = self._get_repo(session)
            task = await repo.get_by_mr_iid(mr_iid)
            if task is None:
                logger.warning("qa_result_task_not_found", mr_iid=mr_iid)
                return []

            if task.status != "reviewing":
                logger.info(
                    "qa_result_ignored_wrong_status",
                    mr_iid=mr_iid,
                    status=task.status,
                )
                return []

            collector = self._get_result_collector(repo, DevWorkflowLogRepository(session))
            if not collector:
                logger.warning(
                    "result_collector_not_available",
                    msg="Cannot process QA result — GitLab client not configured",
                )
                return []

            result = await collector.handle_qa_result(task, event.payload)
            await session.commit()
            return result

    # --- Session / repo helpers ---

    def _get_session(self):
        """Get an async session context manager."""
        if self._db_manager is not None:
            return self._db_manager.session()
        # Fallback: import module-level db_manager
        from ..db.database import db_manager
        return db_manager.session()

    def _get_repo(self, session) -> DevTaskRepository:
        """Get a DevTaskRepository for the given session (or fallback to injected)."""
        if self._repo is not None:
            return self._repo
        return DevTaskRepository(session)

    def _get_result_collector(self, repo, log_repo) -> ResultCollector | None:
        """Build a ResultCollector from available dependencies."""
        if self._result_collector is not None:
            return self._result_collector
        if self._gitlab_client is None:
            return None
        return ResultCollector(
            repo=repo,
            log_repo=log_repo,
            gitlab=self._gitlab_client,
            notifier=self._notifier or build_dev_notifier(),
            security_scanner=self._scanner or SecurityScanner(),
        )
