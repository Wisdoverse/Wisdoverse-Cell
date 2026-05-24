"""Ports for PJM decomposition persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from shared.core.identifiers import OpenProjectProjectId, WorkPackageId
from shared.schemas.event import Event

from .domain.lifecycle.decomposition_lifecycle import DecompositionStatus


class PJMDecompositionRecord(Protocol):
    """Read model exposed by decomposition persistence."""

    id: Any
    wp_id: WorkPackageId
    project_id: OpenProjectProjectId
    status: DecompositionStatus
    assignee_id: int | None
    decompose_result: dict[str, Any] | None
    created_at: Any
    updated_at: Any
    approved_by: str | None


class PJMDecompositionTransaction(Protocol):
    """Transaction-scoped decomposition persistence operations."""

    completed: bool

    async def create(
        self,
        wp_id: WorkPackageId,
        project_id: OpenProjectProjectId,
        decompose_result: dict[str, Any],
        assignee_id: int | None = None,
    ) -> PJMDecompositionRecord:
        """Create a decomposition record."""

    async def get_by_wp_id(self, wp_id: WorkPackageId) -> PJMDecompositionRecord | None:
        """Fetch one decomposition record by OpenProject work-package id."""

    async def update_status(
        self,
        wp_id: WorkPackageId,
        status: DecompositionStatus,
        approved_by: str | None = None,
    ) -> bool:
        """Update decomposition status."""

    async def delete_by_wp_id(self, wp_id: WorkPackageId) -> bool:
        """Delete a decomposition record by OpenProject work-package id."""

    async def stage_event(self, event: Event) -> None:
        """Stage an integration event in the same local transaction."""

    async def commit(self) -> None:
        """Commit decomposition and staged-event mutations."""

    async def rollback(self) -> None:
        """Rollback incomplete or failed decomposition mutations."""


class PJMDecompositionStore(Protocol):
    """Persistence port for PJM decomposition workflows."""

    def transaction(self) -> AbstractAsyncContextManager[PJMDecompositionTransaction]:
        """Open a transaction-scoped persistence boundary."""

    async def list_stale_pending(
        self,
        *,
        older_than_hours: int = 24,
    ) -> list[PJMDecompositionRecord]:
        """Return decomposition records pending longer than the threshold."""
