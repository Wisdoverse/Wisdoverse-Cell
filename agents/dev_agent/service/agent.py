"""DevAgent — Thin Orchestrator for PJM -> AgentForge -> QA workflow."""
from __future__ import annotations

from typing import TYPE_CHECKING

from shared.config import settings
from shared.control_plane import ApprovalGateService
from shared.core import EventPublisher, request_error
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import LLMGateway
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..adapters.agentforge_client import ForgeClient, ForgeClientError
from ..app.metrics import (
    TASKS_FAILED,
    WORKFLOWS_CREATED,
)
from ..core.event_use_cases import DevEventUseCase
from ..core.health_ports import DevHealthStore
from ..core.input_sanitizer import InputSanitizer
from ..core.notifier import DevNotifier
from ..core.outbox_ports import DevEventOutboxStore
from ..core.repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from ..core.request_use_cases import DevRequestUseCase
from ..core.result_collector import ResultCollector
from ..core.risk_assessor import TaskRiskAssessor
from ..core.security_scanner import SecurityScanner
from ..core.tool_router import ToolRouter
from ..core.workflow_execution_use_cases import DevWorkflowExecutionUseCase
from ..core.workflow_planner import WorkflowPlanner
from ..core.workflow_validator import WorkflowValidator
from ..db.health_store import SqlAlchemyDevHealthStore
from ..db.outbox_store import SqlAlchemyDevEventOutboxStore
from ..db.task_store import SqlAlchemyDevTaskStore
from ..db.workflow_log_store import SqlAlchemyDevWorkflowLogStore
from ..models.schemas import RiskLevel, SanitizedTask
from .config_factory import build_dev_core_config
from .notifier_factory import build_dev_notifier

if TYPE_CHECKING:
    from ..adapters.gitlab_client import GitLabClient
    from ..db.database import DatabaseManager

logger = get_logger("dev_agent.service")


class DevAgent(BaseAgent):
    def __init__(
        self,
        bus: EventBus | None = None,
        event_publisher: EventPublisher | None = None,
        outbox_store: DevEventOutboxStore | None = None,
        health_store: DevHealthStore | None = None,
    ):
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
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._sanitizer = InputSanitizer()
        self._risk_assessor = TaskRiskAssessor()
        self._validator = WorkflowValidator()
        self._router = ToolRouter()
        self._core_config = build_dev_core_config()
        self._planner = WorkflowPlanner(LLMGateway(), config=self._core_config)

        self._forge: ForgeClient | None = None
        self._db_manager: DatabaseManager | None = None
        self._outbox_store = outbox_store
        self._health_store = health_store
        self._gitlab_client: GitLabClient | None = None
        self._notifier: DevNotifier | None = None
        self._scanner: SecurityScanner | None = None

        # Legacy per-session repos (kept for backward compat in tests)
        self._repo: DevTaskRepositoryPort | None = None
        self._log_repo: DevWorkflowLogRepositoryPort | None = None
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

    def set_repository(self, repo: DevTaskRepositoryPort) -> None:
        """Inject repository after DB session is available."""
        self._repo = repo

    def set_log_repository(self, log_repo: DevWorkflowLogRepositoryPort) -> None:
        """Inject workflow log repository after DB session is available."""
        self._log_repo = log_repo

    def set_result_collector(self, collector: ResultCollector) -> None:
        """Inject result collector after dependencies are available."""
        self._result_collector = collector

    def _has_db(self) -> bool:
        """Check if database is available (either db_manager or injected repo)."""
        return self._db_manager is not None or self._repo is not None

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> DevEventUseCase:
        return DevEventUseCase(
            sanitizer=self._sanitizer,
            risk_assessor=self._risk_assessor,
            has_db=self._has_db,
            session_factory=self._get_session,
            repo_factory=self._get_repo,
            log_repo_factory=self._get_log_repo,
            result_collector_factory=self._get_result_collector,
            task_processor=self._process_single_task,
            event_factory=self,
        )

    async def handle_request(self, request: dict) -> dict:
        standard = await self.handle_standard_request(request)
        if standard is not None:
            return standard
        action = request.get("action")

        if not self._has_db():
            if action in ("list_active_workflows", "list_failed"):
                return {"workflows": []}
            return request_error("Database not initialized", "database_not_initialized")

        async with self._get_session() as session:
            repo = self._get_repo(session)
            result = await self._request_use_case(session, repo).handle(request)
            await session.commit()
            return result

    def _request_use_case(self, session, repo: DevTaskRepositoryPort) -> DevRequestUseCase:
        return DevRequestUseCase(
            repo=repo,
            log_repo=self._get_log_repo(session),
            approval_gate=self._approval_gate,
            workflow_executor=self,
        )

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the development execution boundary."""
        checks = {
            "database": False,
            "notifier": self._notifier is not None,
        }
        if settings.agentforge_api_url:
            checks["agentforge_client"] = self._forge is not None
        if settings.dev_gitlab_api_url and settings.dev_gitlab_project_id:
            checks["gitlab_client"] = self._gitlab_client is not None

        health_store = self._get_health_store()
        if health_store is not None:
            checks["database"] = await health_store.is_database_ready()
        elif self._repo is not None:
            checks["database"] = True

        return checks

    def _get_health_store(self) -> DevHealthStore | None:
        if self._health_store is not None:
            return self._health_store
        if self._db_manager is None:
            return None
        self._health_store = SqlAlchemyDevHealthStore(self._db_manager)
        return self._health_store

    async def publish_pending_dev_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending Dev outbox events."""
        outbox_store = self._get_outbox_store()
        if outbox_store is None:
            raise RuntimeError("dev_outbox_store_not_started")

        rows = await outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            if await self.publish_staged_dev_event(event):
                published += 1
            else:
                failed += 1

        logger.info(
            "dev_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_staged_dev_events(self, events: list[Event]) -> dict[str, int]:
        """Publish Dev events already committed to the local outbox."""
        published = 0
        failed = 0
        for event in events:
            if await self.publish_staged_dev_event(event):
                published += 1
            else:
                failed += 1
        return {"total": len(events), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Dev event before EventBus delivery."""
        outbox_store = self._get_outbox_store()
        if outbox_store is None:
            raise RuntimeError("dev_outbox_store_not_started")
        await outbox_store.add(event)
        return await self.publish_staged_dev_event(event)

    async def publish_staged_dev_event(self, event: Event) -> bool:
        """Publish one outbox-staged Dev event and record its delivery status."""
        try:
            await self._event_bus.connect()
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_dev_event_published(event)
            return True
        except Exception as exc:
            await self._mark_dev_event_failed(event, exc)
            logger.error(
                "dev_outbox_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )
            return False

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a Dev outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _mark_dev_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published Dev outbox event."""
        outbox_store = self._get_outbox_store()
        if outbox_store is None:
            logger.warning("dev_outbox_mark_published_skipped", event_id=event.event_id)
            return
        try:
            await outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "dev_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_dev_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for a Dev outbox publish attempt."""
        outbox_store = self._get_outbox_store()
        if outbox_store is None:
            logger.warning(
                "dev_outbox_mark_failed_skipped",
                event_id=event.event_id,
                publish_error=str(error),
            )
            return
        try:
            await outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "dev_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

    def _get_outbox_store(self) -> DevEventOutboxStore | None:
        """Return the Dev outbox store, creating the SQLAlchemy adapter lazily."""
        if self._outbox_store is None and self._db_manager is not None:
            self._outbox_store = SqlAlchemyDevEventOutboxStore(self._db_manager)
        return self._outbox_store

    def _workflow_execution_use_case(self) -> DevWorkflowExecutionUseCase:
        return DevWorkflowExecutionUseCase(
            planner=self._planner,
            validator=self._validator,
            router=self._router,
            approval_gate=self._approval_gate,
            event_factory=self,
            forge=self._forge,
            max_concurrent_workflows=settings.dev_max_concurrent_workflows,
            agentforge_project_id=settings.dev_agentforge_project_id,
            workflow_executor=self,
            forge_failure_types=(ForgeClientError,),
            record_task_failure=self._record_task_failure,
            record_workflow_created=self._record_workflow_created,
        )

    async def _process_single_task(
        self,
        sanitized: SanitizedTask,
        risk: RiskLevel,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._workflow_execution_use_case().process_single_task(
            sanitized,
            risk,
            repo,
            log_repo,
            trace_id=trace_id,
        )

    async def _plan_and_execute(
        self,
        sanitized,
        task_record,
        repo,
        log_repo,
        risk,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._workflow_execution_use_case().plan_and_execute(
            sanitized,
            task_record,
            repo,
            log_repo,
            risk,
            trace_id=trace_id,
        )

    async def _request_workflow_approval(
        self,
        *,
        sanitized: SanitizedTask,
        task_id: str,
        plan_json: dict,
    ) -> str | None:
        return await self._workflow_execution_use_case().request_workflow_approval(
            sanitized=sanitized,
            task_id=task_id,
            plan_json=plan_json,
        )

    async def execute_workflow(
        self,
        plan,
        task_record,
        repo: DevTaskRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._execute_workflow(plan, task_record, repo, trace_id=trace_id)

    async def _execute_workflow(
        self,
        plan,
        task_record,
        repo,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._workflow_execution_use_case().execute_workflow(
            plan,
            task_record,
            repo,
            trace_id=trace_id,
        )

    def _record_task_failure(self, reason: str) -> None:
        TASKS_FAILED.labels(reason=reason).inc()

    def _record_workflow_created(self) -> None:
        WORKFLOWS_CREATED.inc()

    # --- Session / repo helpers ---

    def _get_session(self):
        """Get an async session context manager."""
        if self._db_manager is not None:
            return self._db_manager.session()
        # Fallback: import module-level db_manager
        from ..db.database import db_manager
        return db_manager.session()

    def _get_repo(self, session) -> DevTaskRepositoryPort:
        """Get a task store for the given session (or fallback to injected)."""
        if self._repo is not None:
            return self._repo
        return SqlAlchemyDevTaskStore(session)

    def _get_log_repo(self, session) -> DevWorkflowLogRepositoryPort:
        """Get a workflow-log store for the given session."""
        if self._log_repo is not None:
            return self._log_repo
        return SqlAlchemyDevWorkflowLogStore(session)

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
            config=self._core_config,
        )
