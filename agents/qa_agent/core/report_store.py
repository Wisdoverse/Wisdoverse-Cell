"""Ports for QA report persistence."""

from typing import Any, Protocol

from ..models.schemas import AcceptanceExecutionResult, QARunRequest
from .run_store import QAAcceptanceRunRecord


class QAReportStore(Protocol):
    """Persistence port for QA acceptance report results."""

    async def save_execution_result(
        self,
        request: QARunRequest,
        result: AcceptanceExecutionResult,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
        notification_summary: dict[str, Any] | None = None,
    ) -> QAAcceptanceRunRecord:
        """Persist an acceptance execution result."""
