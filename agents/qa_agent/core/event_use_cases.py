"""Application use cases for QA agent event dispatch."""
from __future__ import annotations

from typing import Protocol

from shared.schemas.event import Event, EventTypes
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


class QAAcceptanceRequestEnvelopePort(Protocol):
    """Translated QA-local request plus source-system context."""

    request: QARunRequest


class QAAcceptanceRequestTranslatorPort(Protocol):
    """Translates external QA-trigger events into QA-local run requests."""

    def from_code_committed(self, event: Event) -> QAAcceptanceRequestEnvelopePort:
        """Translate one code.committed event."""

    def from_run_requested(self, event: Event) -> QAAcceptanceRequestEnvelopePort:
        """Translate one qa.run-requested event."""


class QAEventUseCase:
    """Dispatch QA events without leaking event parsing into the service shell."""

    def __init__(
        self,
        *,
        runner: QAEventRunnerPort,
        request_translator: QAAcceptanceRequestTranslatorPort,
    ) -> None:
        self._runner = runner
        self._request_translator = request_translator

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
        translated = self._request_translator.from_code_committed(event)
        await self._runner.run_acceptance(
            translated.request,
            trace_id=_trace_id(event),
            trigger_event_id=event.event_id,
        )

    async def _handle_run_requested(self, event: Event) -> None:
        translated = self._request_translator.from_run_requested(event)
        await self._runner.run_acceptance(
            translated.request,
            trace_id=_trace_id(event),
            trigger_event_id=event.event_id,
        )


def _trace_id(event: Event) -> str | None:
    return event.metadata.trace_id if event.metadata else None
