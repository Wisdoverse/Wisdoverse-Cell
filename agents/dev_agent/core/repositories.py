"""Repository ports for dev-agent core use cases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from shared.core.identifiers import DevTaskId, WorkPackageId

from .domain.lifecycle.task_lifecycle import TaskStatus
from .domain.task_values import RiskLevel


class DevTaskRecord(Protocol):
    """Task fields consumed by dev-agent core use cases."""

    id: DevTaskId
    wp_id: WorkPackageId
    status: TaskStatus
    task_title: str | None
    risk_level: RiskLevel | str | None
    created_at: datetime | None
    updated_at: datetime | None
    workflow_id: str | None
    workflow_started_at: datetime | None
    last_polled_at: datetime | None
    retry_count: int
    mr_url: str | None
    error_message: str | None
    failed_step: str | None


@dataclass(frozen=True, slots=True)
class DevTaskSnapshot:
    """Immutable task record returned through the Dev task port."""

    id: DevTaskId
    wp_id: WorkPackageId
    status: TaskStatus
    task_title: str | None
    risk_level: RiskLevel | str | None
    created_at: datetime | None
    updated_at: datetime | None
    workflow_id: str | None
    workflow_started_at: datetime | None
    last_polled_at: datetime | None
    retry_count: int
    mr_url: str | None
    error_message: str | None
    failed_step: str | None

    @classmethod
    def from_record(cls, record: Any) -> "DevTaskSnapshot":
        """Map a persistence row or test double into the core task snapshot."""
        return cls(
            id=DevTaskId(str(record.id)),
            wp_id=WorkPackageId(int(record.wp_id)),
            status=TaskStatus(str(record.status)),
            task_title=getattr(record, "task_title", None),
            risk_level=getattr(record, "risk_level", None),
            created_at=getattr(record, "created_at", None),
            updated_at=getattr(record, "updated_at", None),
            workflow_id=getattr(record, "workflow_id", None),
            workflow_started_at=getattr(record, "workflow_started_at", None),
            last_polled_at=getattr(record, "last_polled_at", None),
            retry_count=int(getattr(record, "retry_count", 0) or 0),
            mr_url=getattr(record, "mr_url", None),
            error_message=getattr(record, "error_message", None),
            failed_step=getattr(record, "failed_step", None),
        )


class DevTaskRepositoryPort(Protocol):
    """Persistence operations required by dev-agent core use cases."""

    async def create_task(
        self,
        wp_id: WorkPackageId,
        task_title: str,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
    ) -> DevTaskRecord | None:
        """Create a task record if the work package has not been seen."""

    async def get_by_wp_id(self, wp_id: WorkPackageId) -> DevTaskRecord | None:
        """Return one task by OpenProject work-package id."""

    async def get_by_id(self, task_id: DevTaskId) -> DevTaskRecord | None:
        """Return one task by internal task id."""

    async def get_by_mr_iid(self, mr_iid: int) -> DevTaskRecord | None:
        """Return one task by GitLab merge-request iid."""

    async def update_status(
        self,
        task_id: DevTaskId,
        new_status: TaskStatus,
        **kwargs: Any,
    ) -> bool:
        """Persist a task lifecycle transition."""

    async def mark_polled(self, task_id: DevTaskId, *, polled_at: datetime) -> bool:
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


@dataclass(frozen=True, slots=True)
class DevWorkflowLogSnapshot:
    """Immutable workflow-log record returned through the Dev workflow-log port."""

    workflow_json: dict | None

    @classmethod
    def from_record(cls, record: Any) -> "DevWorkflowLogSnapshot":
        """Map a persistence row or test double into the core workflow-log snapshot."""
        return cls(workflow_json=getattr(record, "workflow_json", None))


class DevWorkflowLogRepositoryPort(Protocol):
    """Persistence operations required for workflow logs."""

    async def create_log(
        self,
        task_id: DevTaskId,
        **kwargs: Any,
    ) -> DevWorkflowLogRecord:
        """Persist a workflow log entry."""

    async def get_by_task_id(self, task_id: DevTaskId) -> DevWorkflowLogRecord | None:
        """Return the latest workflow log for a task."""
