"""Application facade for the QA Agent service shell."""

from __future__ import annotations

from typing import Any

from shared.core.identifiers import AcceptanceRunId
from shared.schemas.event import Event

from ..models.schemas import AcceptanceExecutionResult, QARunRequest, QARunStats
from .acceptance_execution_use_cases import QAAcceptanceExecutionUseCase
from .outbox_delivery_use_cases import QAOutboxDeliveryUseCase
from .run_query_use_cases import QARunQueryUseCase


class QAApplicationFacade:
    """Coordinate QA application use cases behind the runtime agent boundary."""

    def __init__(
        self,
        *,
        acceptance_execution: QAAcceptanceExecutionUseCase,
        run_queries: QARunQueryUseCase,
        outbox_delivery: QAOutboxDeliveryUseCase,
    ) -> None:
        self._acceptance_execution = acceptance_execution
        self._run_queries = run_queries
        self._outbox_delivery = outbox_delivery

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        return await self._acceptance_execution.run_acceptance(
            request,
            trace_id=trace_id,
            trigger_event_id=trigger_event_id,
        )

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._run_queries.list_runs(
            agent_name=agent_name,
            limit=limit,
            offset=offset,
        )

    async def get_run(self, run_id: AcceptanceRunId) -> dict[str, Any] | None:
        return await self._run_queries.get_run(run_id)

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        return await self._run_queries.get_stats(agent_name=agent_name, days=days)

    async def publish_pending_qa_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery.publish_pending_events(limit=limit)

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery.publish_event_via_outbox(event)
