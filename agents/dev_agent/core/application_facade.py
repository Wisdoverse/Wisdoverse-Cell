"""Application facade for the Dev Agent service shell."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared.core import EventPublisher
from shared.schemas.event import Event

from ..models.schemas import RiskLevel, SanitizedTask, WorkflowPlan
from .event_use_cases import DevEventUseCase
from .outbox_delivery_use_cases import DevOutboxDeliveryUseCase
from .outbox_ports import DevEventOutboxStore
from .repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from .request_use_cases import DevRequestBoundaryUseCase, DevRequestUseCase
from .result_collector import ResultCollector
from .unit_of_work_ports import DevUnitOfWorkFactory
from .workflow_execution_use_cases import DevWorkflowExecutionUseCase


class DevApplicationFacade:
    """Coordinate Dev application use cases behind the runtime agent boundary."""

    def __init__(
        self,
        *,
        standard_request_handler: Any,
        sanitizer: Any,
        risk_assessor: Any,
        has_db: Callable[[], bool],
        uow_factory: DevUnitOfWorkFactory,
        result_collector_factory: Callable[
            [DevTaskRepositoryPort, DevWorkflowLogRepositoryPort],
            ResultCollector | None,
        ],
        event_factory: Any,
        approval_gate_provider: Callable[[], Any],
        planner: Any,
        validator: Any,
        router: Any,
        forge_provider: Callable[[], Any],
        outbox_store_getter: Callable[[], DevEventOutboxStore | None],
        event_bus: Any,
        event_publisher: EventPublisher,
        workflow_executor: Any,
        max_concurrent_workflows_provider: Callable[[], int],
        agentforge_project_id_provider: Callable[[], str | None],
        forge_failure_types: tuple[type[BaseException], ...],
        record_task_failure: Callable[[str], None],
        record_workflow_created: Callable[[], None],
    ) -> None:
        self._standard_request_handler = standard_request_handler
        self._sanitizer = sanitizer
        self._risk_assessor = risk_assessor
        self._has_db = has_db
        self._uow_factory = uow_factory
        self._result_collector_factory = result_collector_factory
        self._event_factory = event_factory
        self._approval_gate_provider = approval_gate_provider
        self._planner = planner
        self._validator = validator
        self._router = router
        self._forge_provider = forge_provider
        self._outbox_store_getter = outbox_store_getter
        self._event_bus = event_bus
        self._event_publisher = event_publisher
        self._workflow_executor = workflow_executor
        self._max_concurrent_workflows_provider = max_concurrent_workflows_provider
        self._agentforge_project_id_provider = agentforge_project_id_provider
        self._forge_failure_types = forge_failure_types
        self._record_task_failure = record_task_failure
        self._record_workflow_created = record_workflow_created

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> DevEventUseCase:
        return DevEventUseCase(
            sanitizer=self._sanitizer,
            risk_assessor=self._risk_assessor,
            has_db=self._has_db,
            uow_factory=self._uow_factory,
            result_collector_factory=self._result_collector_factory,
            task_processor=self.process_single_task,
            event_factory=self._event_factory,
        )

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._request_boundary_use_case().handle(request)

    def _request_boundary_use_case(self) -> DevRequestBoundaryUseCase:
        return DevRequestBoundaryUseCase(
            standard_request_handler=self._standard_request_handler,
            has_db=self._has_db,
            uow_factory=self._uow_factory,
            request_use_case_factory=self._request_use_case,
        )

    def _request_use_case(
        self,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
    ) -> DevRequestUseCase:
        return DevRequestUseCase(
            repo=repo,
            log_repo=log_repo,
            approval_gate=self._approval_gate_provider(),
            workflow_executor=self._workflow_executor,
        )

    async def publish_pending_dev_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(limit=limit)

    async def publish_staged_dev_events(self, events: list[Event]) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_staged_events(events)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> DevOutboxDeliveryUseCase:
        outbox_store = self._outbox_store_getter()
        if outbox_store is None:
            raise RuntimeError("dev_outbox_store_not_started")
        return DevOutboxDeliveryUseCase(
            outbox_store=outbox_store,
            event_bus=self._event_bus,
            event_publisher=self._event_publisher,
        )

    async def process_single_task(
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

    async def plan_and_execute(
        self,
        sanitized: SanitizedTask,
        task_record: Any,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        risk: RiskLevel,
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

    async def request_workflow_approval(
        self,
        *,
        sanitized: SanitizedTask,
        task_id: str,
        plan_json: dict[str, Any],
    ) -> str | None:
        return await self._workflow_execution_use_case().request_workflow_approval(
            sanitized=sanitized,
            task_id=task_id,
            plan_json=plan_json,
        )

    async def execute_workflow(
        self,
        plan: WorkflowPlan,
        task_record: Any,
        repo: DevTaskRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        return await self._workflow_execution_use_case().execute_workflow(
            plan,
            task_record,
            repo,
            trace_id=trace_id,
        )

    def _workflow_execution_use_case(self) -> DevWorkflowExecutionUseCase:
        return DevWorkflowExecutionUseCase(
            planner=self._planner,
            validator=self._validator,
            router=self._router,
            approval_gate=self._approval_gate_provider(),
            event_factory=self._event_factory,
            forge=self._forge_provider(),
            max_concurrent_workflows=self._max_concurrent_workflows_provider(),
            agentforge_project_id=self._agentforge_project_id_provider(),
            workflow_executor=self._workflow_executor,
            forge_failure_types=self._forge_failure_types,
            record_task_failure=self._record_task_failure,
            record_workflow_created=self._record_workflow_created,
        )
