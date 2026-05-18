"""Ports for QA acceptance run persistence."""

from typing import Any, Protocol

from ..models.schemas import QARunStats


class QAAcceptanceRunRecord(Protocol):
    """Read model exposed by QA acceptance run persistence."""

    id: str
    agent_name: str
    commit_sha: str | None
    mr_iid: int | None
    trigger: str
    level: str
    files_changed: list[str] | None
    l0_status: str
    l1_status: str
    l2_status: str
    total_checks: int
    l0_failure_count: int
    l1_warning_count: int
    duration_seconds: float
    runner_exit_code: int
    raw_report: dict[str, Any] | None
    report_markdown: str | None
    notification_summary: dict[str, Any] | None
    created_at: Any
    completed_at: Any


class QAAcceptanceRunStore(Protocol):
    """Persistence port for QA acceptance run reads and updates."""

    async def get_by_id(self, run_id: str) -> QAAcceptanceRunRecord | None:
        """Fetch one acceptance run by id."""

    async def get_by_trigger_event_id(
        self,
        trigger_event_id: str | None,
    ) -> QAAcceptanceRunRecord | None:
        """Fetch one acceptance run by idempotency event id."""

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[QAAcceptanceRunRecord]:
        """List acceptance runs."""

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        """Return aggregate run statistics."""

    async def update_notification_summary(
        self,
        run_id: str,
        notification_summary: dict[str, Any],
    ) -> bool:
        """Update notification delivery summary for a run."""
