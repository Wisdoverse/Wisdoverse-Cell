"""Ports for control-plane agent execution operations."""
from __future__ import annotations

from typing import Any, Protocol


class ControlPlaneAgentOperationStore(Protocol):
    """Persistence operations required by agent wakeup and scheduling."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return one company context."""

    async def get_agent_role(self, *, company_id: str, agent_id: str) -> Any | None:
        """Return one agent role."""

    async def list_agent_roles(
        self,
        *,
        company_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return agent roles for one company."""

    async def create_agent_run(self, run: Any) -> Any:
        """Create an agent run."""

    async def get_agent_run(self, run_id: str) -> Any | None:
        """Return one agent run."""

    async def list_agent_runs(
        self,
        *,
        company_id: str,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return agent runs for one company."""

    async def update_agent_run_status(
        self,
        run_id: str,
        status: Any,
        **values: Any,
    ) -> Any | None:
        """Update an agent run status."""

    async def list_approvals(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return approvals for a run."""

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return budget usage for a run."""

    async def list_audit_events(
        self,
        *,
        company_id: str,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return audit events for a run."""

    async def create_artifact(self, artifact: Any) -> Any:
        """Create an artifact."""

    async def append_audit_event(self, event: Any) -> Any:
        """Append an audit event."""
