"""Repository ports for dev-agent core use cases."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class DevTaskRecord(Protocol):
    """Task fields consumed by dev-agent core use cases."""

    id: str
    wp_id: int
    status: str
    task_title: str | None
    risk_level: str | None
    created_at: datetime | None
    updated_at: datetime | None
    workflow_id: str | None
    workflow_started_at: datetime | None
    last_polled_at: datetime | None
    retry_count: int
    mr_url: str | None


class DevTaskRepositoryPort(Protocol):
    """Persistence operations required by dev-agent core use cases."""

    async def create_task(
        self,
        wp_id: int,
        task_title: str,
        risk_level: str = "MEDIUM",
    ) -> DevTaskRecord | None:
        """Create a task record if the work package has not been seen."""

    async def get_by_wp_id(self, wp_id: int) -> DevTaskRecord | None:
        """Return one task by OpenProject work-package id."""

    async def get_by_id(self, task_id: str) -> DevTaskRecord | None:
        """Return one task by internal task id."""

    async def get_by_mr_iid(self, mr_iid: int) -> DevTaskRecord | None:
        """Return one task by GitLab merge-request iid."""

    async def update_status(
        self,
        task_id: str,
        new_status: str,
        **kwargs: Any,
    ) -> bool:
        """Persist a task lifecycle transition."""

    async def mark_polled(self, task_id: str, *, polled_at: datetime) -> bool:
        """Persist that an external workflow status poll was attempted."""

    async def list_active_tasks(self) -> list[DevTaskRecord]:
        """Return active workflow tasks."""

    async def list_pending_tasks(self, limit: int = 5) -> list[DevTaskRecord]:
        """Return tasks waiting for execution slots."""

    async def list_planning_tasks(self, limit: int = 5) -> list[DevTaskRecord]:
        """Return tasks that should re-enter planning."""

    async def list_failed_tasks(self, limit: int = 50) -> list[DevTaskRecord]:
        """Return recently failed workflow tasks."""

    async def count_active_workflows(self) -> int:
        """Count workflows currently in progress."""

    async def expire_stale_pending(self, hours: int = 24) -> int:
        """Expire pending tasks older than the configured age."""


class DevWorkflowLogRecord(Protocol):
    """Workflow log fields consumed by dev-agent use cases."""

    workflow_json: dict | None


class DevWorkflowLogRepositoryPort(Protocol):
    """Persistence operations required for workflow logs."""

    async def create_log(self, task_id: str, **kwargs: Any) -> DevWorkflowLogRecord:
        """Persist a workflow log entry."""

    async def get_by_task_id(self, task_id: str) -> DevWorkflowLogRecord | None:
        """Return the latest workflow log for a task."""
