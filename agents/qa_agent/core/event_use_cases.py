"""Application use cases for QA agent event dispatch."""
from __future__ import annotations

from typing import Protocol

from shared.schemas.event import Event, EventTypes
from shared.schemas.event_payloads import CodeCommittedPayload, QARunRequestedPayload
from shared.utils.logger import get_logger

from ..models.schemas import AcceptanceExecutionResult, QARunRequest

logger = get_logger("qa_agent.events")


class QAEventRunnerPort(Protocol):
    """QA run orchestration required by event handling."""

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        """Run one acceptance check."""


class QAEventUseCase:
    """Dispatch QA events without leaking event parsing into the service shell."""

    def __init__(self, *, runner: QAEventRunnerPort) -> None:
        self._runner = runner

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.CODE_COMMITTED:
            await self._handle_code_committed(event)
        elif event.event_type == EventTypes.QA_RUN_REQUESTED:
            if event.payload.get("instruction"):
                logger.info(
                    "coordinator_instruction_received",
                    instruction=event.payload.get("instruction"),
                    workflow_id=event.payload.get("workflow_id"),
                )
            await self._handle_run_requested(event)
        return []

    async def _handle_code_committed(self, event: Event) -> None:
        payload = CodeCommittedPayload.model_validate(event.payload)
        request = QARunRequest(
            agent_name=payload.agent_name,
            level="all",
            commit_sha=payload.commit_sha,
            diff_ref=payload.diff_ref,
            files_changed=payload.files_changed,
            branch=payload.branch,
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            trigger="event",
            requested_by="code.committed",
        )
        await self._runner.run_acceptance(
            request,
            trace_id=_trace_id(event),
            trigger_event_id=event.event_id,
        )

    async def _handle_run_requested(self, event: Event) -> None:
        payload = QARunRequestedPayload.model_validate(event.payload)
        request = QARunRequest(
            agent_name=payload.agent_name,
            level=payload.level,
            commit_sha=payload.commit_sha,
            files_changed=payload.files_changed,
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            trigger="event",
            requested_by=payload.requested_by,
            reason=payload.reason,
        )
        await self._runner.run_acceptance(
            request,
            trace_id=_trace_id(event),
            trigger_event_id=event.event_id,
        )


def _trace_id(event: Event) -> str | None:
    return event.metadata.trace_id if event.metadata else None
