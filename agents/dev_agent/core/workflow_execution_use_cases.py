"""Application use cases for Dev workflow execution."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from shared.control_plane import ApprovalCategory
from shared.core.identifiers import DevTaskId, WorkPackageId
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import SanitizedTask, WorkflowNode, WorkflowPlan
from .domain.delivery_policy import DevDeliveryWorkflowPolicy
from .domain.lifecycle.task_lifecycle import (
    AWAITING_APPROVAL,
    EXECUTING,
    FAILED,
    PLANNING,
)
from .domain.task_values import RiskLevel
from .repositories import DevTaskRecord, DevTaskRepositoryPort, DevWorkflowLogRepositoryPort
from .workflow_planner import inject_project_id

logger = get_logger("dev_agent.workflow_execution")


class DevWorkflowPlannerPort(Protocol):
    """Plans an AgentForge workflow for a sanitized task."""

    async def plan(self, task: SanitizedTask) -> WorkflowPlan | None:
        """Return a workflow plan or None when planning fails."""


class DevWorkflowValidationResultPort(Protocol):
    """Validation result consumed by the execution use case."""

    is_valid: bool
    violations: list[str]


class DevWorkflowValidatorPort(Protocol):
    """Validates generated AgentForge workflow plans."""

    def validate(self, plan: WorkflowPlan) -> DevWorkflowValidationResultPort:
        """Return validation result for one workflow plan."""


class DevToolRouterPort(Protocol):
    """Selects the CLI tool for each workflow node."""

    def route(self, node: WorkflowNode) -> str:
        """Return the CLI tool name for one workflow node."""


class DevWorkflowApprovalGatePort(Protocol):
    """Control-plane approval boundary for high-risk workflow execution."""

    enforced: bool

    async def request_approval(
        self,
        *,
        category: ApprovalCategory,
        proposed_action: str,
        reason: str,
        risk: str,
        rollback_note: str,
        affected_resources: list[str],
    ) -> Any:
        """Create a human approval request."""


class DevWorkflowEventFactoryPort(Protocol):
    """Event factory owned by the service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> Event:
        """Create an event with service identity and trace metadata."""


class DevForgeWorkflowClientPort(Protocol):
    """External AgentForge workflow client boundary."""

    async def create_workflow(self, plan: WorkflowPlan) -> str:
        """Create a remote workflow and return its id."""

    async def run_workflow(self, workflow_id: str) -> None:
        """Start a remote workflow."""


class DevWorkflowExecutorPort(Protocol):
    """Workflow executor boundary used by planning and request approval flows."""

    async def execute_workflow(
        self,
        plan: WorkflowPlan,
        task_record: DevTaskRecord,
        repo: DevTaskRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        """Execute one validated workflow plan."""


RecordTaskFailure = Callable[[str], None]
RecordWorkflowCreated = Callable[[], None]


def _noop_task_failure(_reason: str) -> None:
    return None


def _noop_workflow_created() -> None:
    return None


class DevWorkflowExecutionUseCase:
    """Create, plan, approve, and submit Dev AgentForge workflows."""

    def __init__(
        self,
        *,
        planner: DevWorkflowPlannerPort,
        validator: DevWorkflowValidatorPort,
        router: DevToolRouterPort,
        approval_gate: DevWorkflowApprovalGatePort,
        event_factory: DevWorkflowEventFactoryPort,
        forge: DevForgeWorkflowClientPort | None,
        max_concurrent_workflows: int,
        agentforge_project_id: str | None,
        workflow_executor: DevWorkflowExecutorPort | None = None,
        forge_failure_types: tuple[type[BaseException], ...] = (Exception,),
        record_task_failure: RecordTaskFailure = _noop_task_failure,
        record_workflow_created: RecordWorkflowCreated = _noop_workflow_created,
        workflow_policy: DevDeliveryWorkflowPolicy | None = None,
    ) -> None:
        self._planner = planner
        self._validator = validator
        self._router = router
        self._approval_gate = approval_gate
        self._event_factory = event_factory
        self._forge = forge
        self._max_concurrent_workflows = max_concurrent_workflows
        self._agentforge_project_id = agentforge_project_id
        self._workflow_executor = workflow_executor or self
        self._forge_failure_types = forge_failure_types
        self._record_task_failure = record_task_failure
        self._record_workflow_created = record_workflow_created
        self._workflow_policy = workflow_policy or DevDeliveryWorkflowPolicy()

    async def process_single_task(
        self,
        sanitized: SanitizedTask,
        risk: RiskLevel,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        """Process a sanitized task through create -> plan -> execute."""
        events: list[Event] = []
        wp_id = WorkPackageId(sanitized.wp_id)
        risk = RiskLevel(risk)
        logger.info("task_accepted", wp_id=sanitized.wp_id, risk=risk.value)

        task_record = await repo.create_task(
            wp_id=wp_id,
            task_title=sanitized.title,
            risk_level=risk,
        )
        if task_record is None:
            logger.info("task_already_exists", wp_id=sanitized.wp_id)
            return events

        task_id = DevTaskId(str(task_record.id))
        await log_repo.create_log(
            task_id=task_id,
            workflow_json={"task_input": sanitized.model_dump()},
        )

        active_count = await repo.count_active_workflows()
        capacity = self._workflow_policy.capacity_decision(
            active_count=active_count,
            max_concurrent_workflows=self._max_concurrent_workflows,
        )
        if not capacity.can_start:
            logger.info(
                "task_queued",
                wp_id=sanitized.wp_id,
                active=capacity.active_count,
            )
            return events

        return await self.plan_and_execute(
            sanitized,
            task_record,
            repo,
            log_repo,
            risk,
            trace_id=trace_id,
        )

    async def plan_and_execute(
        self,
        sanitized: SanitizedTask,
        task_record: DevTaskRecord,
        repo: DevTaskRepositoryPort,
        log_repo: DevWorkflowLogRepositoryPort,
        risk: RiskLevel,
        trace_id: str | None = None,
    ) -> list[Event]:
        """Plan a workflow and execute it, or queue it for approval."""
        events: list[Event] = []
        task_id = DevTaskId(str(task_record.id))
        risk = RiskLevel(risk)

        await repo.update_status(task_id, PLANNING)
        plan = await self._planner.plan(sanitized)
        if plan is None:
            await repo.update_status(
                task_id,
                FAILED,
                error_message="Workflow planning failed",
            )
            self._record_task_failure("planning")
            return events

        plan = inject_project_id(plan, self._agentforge_project_id)
        validation = self._validator.validate(plan)
        if not validation.is_valid:
            await repo.update_status(
                task_id,
                FAILED,
                error_message=f"Validation: {'; '.join(validation.violations)}",
            )
            self._record_task_failure("validation")
            return events

        for node in plan.nodes:
            tool = self._router.route(node)
            node.config["cliTool"] = tool

        plan_json = plan.model_dump()
        requires_approval = self._workflow_policy.requires_workflow_approval(risk)
        if requires_approval:
            approval_id = await self.request_workflow_approval(
                sanitized=sanitized,
                task_id=task_id,
                plan_json=plan_json,
            )
            if approval_id:
                plan_json["control_plane_approval_id"] = approval_id

        await log_repo.create_log(
            task_id=task_id,
            workflow_json=plan_json,
        )

        if requires_approval:
            await repo.update_status(task_id, AWAITING_APPROVAL)
            logger.info("task_awaiting_approval", wp_id=sanitized.wp_id)
            return events

        return await self._workflow_executor.execute_workflow(
            plan,
            task_record,
            repo,
            trace_id=trace_id,
        )

    async def request_workflow_approval(
        self,
        *,
        sanitized: SanitizedTask,
        task_id: DevTaskId,
        plan_json: dict[str, Any],
    ) -> str | None:
        """Request control-plane approval for a high-risk workflow."""
        try:
            approval = await self._approval_gate.request_approval(
                category=ApprovalCategory.TECHNICAL,
                proposed_action=(
                    f"Start high-risk AgentForge workflow for WP#{sanitized.wp_id}"
                ),
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

    async def execute_workflow(
        self,
        plan: WorkflowPlan,
        task_record: DevTaskRecord,
        repo: DevTaskRepositoryPort,
        trace_id: str | None = None,
    ) -> list[Event]:
        """Submit a validated workflow to AgentForge and update task status."""
        events: list[Event] = []
        if self._forge is None:
            logger.warning(
                "forge_not_initialized",
                wp_id=task_record.wp_id,
                msg="Skipping execution - ForgeClient not available",
            )
            return events

        try:
            plan = inject_project_id(plan, self._agentforge_project_id)
            workflow_id = await self._forge.create_workflow(plan)
            await self._forge.run_workflow(workflow_id)
            task_id = DevTaskId(str(task_record.id))
            await repo.update_status(
                task_id,
                EXECUTING,
                workflow_id=workflow_id,
                workflow_started_at=datetime.now(UTC),
            )
            self._record_workflow_created()
            events.append(
                self._event_factory.create_event(
                    EventTypes.DEV_WORKFLOW_CREATED,
                    {
                        "task_id": str(task_id),
                        "workflow_id": workflow_id,
                        "node_count": len(plan.nodes),
                    },
                    trace_id=trace_id,
                )
            )
        except Exception as exc:
            if not isinstance(exc, self._forge_failure_types):
                raise
            logger.error(
                "forge_client_error",
                wp_id=task_record.wp_id,
                error=str(exc),
                exc_info=True,
            )
            await repo.update_status(
                DevTaskId(str(task_record.id)),
                FAILED,
                error_message=str(exc),
            )
            self._record_task_failure("forge_error")
        return events
