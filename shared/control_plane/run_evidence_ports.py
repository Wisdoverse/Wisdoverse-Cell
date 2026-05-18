"""Ports for control-plane run evidence artifact creation."""
from __future__ import annotations

from typing import Any, Protocol


class ControlPlaneRunEvidenceStore(Protocol):
    """Persistence operations required to build run evidence artifacts."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return approvals linked to one run."""

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return budget usage linked to one run."""

    async def list_audit_events(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return audit events linked to one run."""

    async def create_artifact(self, artifact: Any) -> Any:
        """Create an artifact."""

    async def append_audit_event(self, event: Any) -> Any:
        """Append an audit event."""
