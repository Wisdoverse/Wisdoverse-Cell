"""Ports for QA report persistence."""

from datetime import datetime
from typing import Any, Protocol

from shared.core.identifiers import AcceptanceRunId

from ..models.schemas import AcceptanceExecutionResult, QARunRequest
from .run_store import QAAcceptanceRunRecord


class QAReportStore(Protocol):
    """Persistence port for QA acceptance report results."""

    async def save_execution_result(
        self,
        request: QARunRequest,
        result: AcceptanceExecutionResult,
        *,
        run_id: AcceptanceRunId | None = None,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
        completed_at: datetime | None = None,
        notification_summary: dict[str, Any] | None = None,
    ) -> QAAcceptanceRunRecord:
        """Persist an acceptance execution result."""
