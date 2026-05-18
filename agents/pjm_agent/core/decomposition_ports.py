"""Ports for PJM decomposition persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from shared.schemas.event import Event


class PJMDecompositionRecord(Protocol):
    """Read model exposed by decomposition persistence."""

    id: Any
    wp_id: int
    project_id: int
    status: str
    assignee_id: int | None
    decompose_result: dict[str, Any] | None
    created_at: Any
    updated_at: Any
    approved_by: str | None


class PJMDecompositionTransaction(Protocol):
    """Transaction-scoped decomposition persistence operations."""

    async def create(
        self,
        wp_id: int,
        project_id: int,
        decompose_result: dict[str, Any],
        assignee_id: int | None = None,
    ) -> PJMDecompositionRecord:
        """Create a decomposition record."""

    async def get_by_wp_id(self, wp_id: int) -> PJMDecompositionRecord | None:
        """Fetch one decomposition record by OpenProject work-package id."""

    async def update_status(
        self,
        wp_id: int,
        status: str,
        approved_by: str | None = None,
    ) -> bool:
        """Update decomposition status."""

    async def delete_by_wp_id(self, wp_id: int) -> bool:
        """Delete a decomposition record by OpenProject work-package id."""

    async def stage_event(self, event: Event) -> None:
        """Stage an integration event in the same local transaction."""


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
