"""DevAgent — Thin Orchestrator for PJM -> AgentForge -> QA workflow."""
from __future__ import annotations

from typing import TYPE_CHECKING

from shared.config import settings
from shared.control_plane import ApprovalGateService
from shared.core import EventPublisher
from shared.core.identifiers import DevTaskId
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import LLMGateway
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..adapters.agentforge_client import ForgeClient, ForgeClientError
from ..app.metrics import (
    TASKS_FAILED,
    WORKFLOWS_CREATED,
)
from ..core.application_facade import DevApplicationFacade
from ..core.health_ports import DevHealthStore
from ..core.health_use_cases import DevHealthUseCase
from ..core.input_sanitizer import InputSanitizer
from ..core.notifier import DevNotifier
from ..core.outbox_ports import DevEventOutboxStore
from ..core.repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from ..core.result_collector import ResultCollector
from ..core.risk_assessor import TaskRiskAssessor
from ..core.security_scanner import SecurityScanner
from ..core.tool_router import ToolRouter
from ..core.workflow_planner import WorkflowPlanner
from ..core.workflow_validator import WorkflowValidator
from ..db.health_store import SqlAlchemyDevHealthStore
from ..db.outbox_store import SqlAlchemyDevEventOutboxStore
from ..db.unit_of_work import (
    InjectedDevUnitOfWorkFactory,
    SqlAlchemyDevSessionUnitOfWorkFactory,
    SqlAlchemyDevUnitOfWorkFactory,
)
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
        self._application = DevApplicationFacade(
            standard_request_handler=self,
            sanitizer=self._sanitizer,
            risk_assessor=self._risk_assessor,
            has_db=self._has_db,
            uow_factory=self._get_unit_of_work,
            result_collector_factory=self._get_result_collector,
            event_factory=self,
            approval_gate_provider=lambda: self._approval_gate,
            planner=self._planner,
            validator=self._validator,
            router=self._router,
            forge_provider=lambda: self._forge,
            outbox_store_getter=self._get_outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
            workflow_executor=self,
            max_concurrent_workflows_provider=(
                lambda: settings.dev_max_concurrent_workflows
            ),
            agentforge_project_id_provider=lambda: settings.dev_agentforge_project_id,
            forge_failure_types=(ForgeClientError,),
            record_task_failure=self._record_task_failure,
            record_workflow_created=self._record_workflow_created,
        )

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
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> DevHealthUseCase:
        return DevHealthUseCase(
            health_store=self._get_health_store(),
            repository_available=self._repo is not None,
            notifier=self._notifier,
            forge=self._forge,
            gitlab_client=self._gitlab_client,
            agentforge_required=bool(settings.agentforge_api_url),
            gitlab_required=bool(
                settings.dev_gitlab_api_url and settings.dev_gitlab_project_id
            ),
        )

    def _get_health_store(self) -> DevHealthStore | None:
        if self._health_store is not None:
            return self._health_store
        if self._db_manager is None:
            return None
        self._health_store = SqlAlchemyDevHealthStore(self._db_manager)
        return self._health_store

    async def publish_pending_dev_events(self, limit: int = 100) -> dict[str, int]:
        return await self._application.publish_pending_dev_events(limit=limit)

    async def publish_staged_dev_events(self, events: list[Event]) -> dict[str, int]:
        return await self._application.publish_staged_dev_events(events)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._application.publish_event_via_outbox(event)

    def _get_outbox_store(self) -> DevEventOutboxStore | None:
        """Return the Dev outbox store, creating the SQLAlchemy adapter lazily."""
        if self._outbox_store is None and self._db_manager is not None:
            self._outbox_store = SqlAlchemyDevEventOutboxStore(self._db_manager)
        return self._outbox_store

    async def _process_single_task(
        self,
        sanitized: SanitizedTask,
        risk: RiskLevel,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._application.process_single_task(
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
        return await self._application.plan_and_execute(
            sanitized,
            task_record,
            repo,
            log_repo,
            risk,
            trace_id=trace_id,
        )

    async def plan_and_execute_existing_task(
        self,
        *,
        sanitized: SanitizedTask,
        task_record,
        repo,
        log_repo,
        risk,
        trace_id: str | None = None,
    ) -> list[Event]:
        """Plan and execute an already-persisted task from scheduler recovery."""
        return await self._application.plan_and_execute(
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
        return await self._application.request_workflow_approval(
            sanitized=sanitized,
            task_id=DevTaskId(str(task_id)),
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
        return await self._application.execute_workflow(
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

    def _get_unit_of_work(self):
        """Open a Dev unit-of-work context for event handling."""
        if self._repo is not None:
            if self._log_repo is None:
                raise RuntimeError("dev_log_repository_not_initialized")
            return InjectedDevUnitOfWorkFactory(
                tasks=self._repo,
                workflow_logs=self._log_repo,
            )()

        db_manager = self._db_manager
        if db_manager is None:
            from ..db.database import db_manager as module_db_manager

            db_manager = module_db_manager

        if "async_session" in vars(db_manager):
            return SqlAlchemyDevUnitOfWorkFactory(db_manager)()
        return SqlAlchemyDevSessionUnitOfWorkFactory(db_manager)()

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
