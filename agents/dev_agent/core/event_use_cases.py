"""Application use cases for Dev agent event dispatch."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import RiskLevel, SanitizedTask, TaskInput
from .input_sanitizer import InputRejectedError
from .repositories import DevTaskRepositoryPort, DevWorkflowLogRepositoryPort

logger = get_logger("dev_agent.events")


class DevTaskSanitizerPort(Protocol):
    """Sanitizes inbound PJM task payloads."""

    def sanitize(self, task_input: TaskInput) -> SanitizedTask:
        """Return a safe task input model."""


class DevRiskAssessorPort(Protocol):
    """Assesses the implementation risk of a sanitized task."""

    def assess(self, task: SanitizedTask) -> RiskLevel:
        """Return the task risk level."""


class DevResultCollectorPort(Protocol):
    """Processes QA callback results for a Dev task."""

    async def handle_qa_result(
        self,
        task: Any,
        qa_payload: dict[str, Any],
    ) -> list[Event]:
        """Handle one QA result payload."""


class DevEventFactoryPort(Protocol):
    """Event factory owned by the service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> Event:
        """Create an event with the service identity."""


DevHasDb = Callable[[], bool]
DevSessionFactory = Callable[[], AbstractAsyncContextManager[Any]]
DevRepoFactory = Callable[[Any], DevTaskRepositoryPort]
DevLogRepoFactory = Callable[[Any], DevWorkflowLogRepositoryPort]
DevResultCollectorFactory = Callable[
    [DevTaskRepositoryPort, DevWorkflowLogRepositoryPort],
    DevResultCollectorPort | None,
]
DevTaskProcessor = Callable[
    [SanitizedTask, RiskLevel, DevTaskRepositoryPort, DevWorkflowLogRepositoryPort],
    Awaitable[list[Event]],
]


class DevEventUseCase:
    """Dispatch and execute Dev event workflows outside the service shell."""

    def __init__(
        self,
        *,
        sanitizer: DevTaskSanitizerPort,
        risk_assessor: DevRiskAssessorPort,
        has_db: DevHasDb,
        session_factory: DevSessionFactory,
        repo_factory: DevRepoFactory,
        log_repo_factory: DevLogRepoFactory,
        result_collector_factory: DevResultCollectorFactory,
        task_processor: DevTaskProcessor,
        event_factory: DevEventFactoryPort,
    ) -> None:
        self._sanitizer = sanitizer
        self._risk_assessor = risk_assessor
        self._has_db = has_db
        self._session_factory = session_factory
        self._repo_factory = repo_factory
        self._log_repo_factory = log_repo_factory
        self._result_collector_factory = result_collector_factory
        self._task_processor = task_processor
        self._event_factory = event_factory

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV:
            return await self._handle_tasks_ready(event)
        if event.event_type == EventTypes.QA_ACCEPTANCE_COMPLETED:
            return await self._handle_qa_result(event)
        return []

    async def _handle_tasks_ready(self, event: Event) -> list[Event]:
        payload = event.payload
        trace_id = _trace_id(event)
        if payload.get("instruction"):
            logger.info(
                "coordinator_instruction_received",
                instruction=payload.get("instruction"),
                workflow_id=payload.get("workflow_id"),
            )

        wp_id = payload.get("wp_id")
        tasks = payload.get("tasks", [])
        events: list[Event] = []
        sanitized_tasks: list[tuple[SanitizedTask, RiskLevel]] = []

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
                        self._event_factory.create_event(
                            EventTypes.DEV_TASK_FAILED,
                            {
                                "wp_id": sanitized.wp_id,
                                "error": (
                                    "CRITICAL risk - requires human implementation"
                                ),
                                "failed_node": "",
                                "runbook_url": "",
                            },
                            trace_id=trace_id,
                        )
                    )
                    continue

                sanitized_tasks.append((sanitized, risk))

            except InputRejectedError as exc:
                logger.warning("task_input_rejected", wp_id=wp_id, reasons=exc.reasons)
            except Exception as exc:
                logger.error(
                    "task_processing_error",
                    wp_id=wp_id,
                    error=str(exc),
                    exc_info=True,
                )
                events.append(
                    self._event_factory.create_event(
                        EventTypes.DEV_TASK_FAILED,
                        {
                            "wp_id": wp_id,
                            "error": str(exc),
                            "failed_node": "",
                            "runbook_url": "",
                        },
                        trace_id=trace_id,
                    )
                )

        if not sanitized_tasks:
            return events

        if not self._has_db():
            logger.warning("db_not_available", msg="Cannot process tasks - no DB")
            return events

        async with self._session_factory() as session:
            repo = self._repo_factory(session)
            log_repo = self._log_repo_factory(session)
            for sanitized, risk in sanitized_tasks:
                try:
                    new_events = await self._task_processor(
                        sanitized,
                        risk,
                        repo,
                        log_repo,
                        trace_id=trace_id,
                    )
                    events.extend(new_events)
                except Exception as exc:
                    logger.error(
                        "task_processing_error",
                        wp_id=sanitized.wp_id,
                        error=str(exc),
                        exc_info=True,
                    )
            await session.commit()
        return events

    async def _handle_qa_result(self, event: Event) -> list[Event]:
        logger.info(
            "qa_result_received",
            event_id=event.event_id,
            trace_id=_trace_id(event),
            payload_keys=sorted(event.payload.keys()),
        )

        mr_iid = event.payload.get("mr_iid")
        if mr_iid is None:
            logger.warning("qa_result_missing_mr_iid")
            return []

        if not self._has_db():
            logger.warning("db_not_available", msg="Cannot process QA result")
            return []

        async with self._session_factory() as session:
            repo = self._repo_factory(session)
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

            log_repo = self._log_repo_factory(session)
            collector = self._result_collector_factory(repo, log_repo)
            if not collector:
                logger.warning(
                    "result_collector_not_available",
                    msg="Cannot process QA result - GitLab client not configured",
                )
                return []

            result = await collector.handle_qa_result(task, event.payload)
            await session.commit()
            return result


def _trace_id(event: Event) -> str | None:
    return event.metadata.trace_id if event.metadata else None
