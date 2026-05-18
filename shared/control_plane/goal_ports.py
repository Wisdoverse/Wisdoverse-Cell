"""Ports for control-plane goal persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, CompanyContext, Goal


class ControlPlaneGoalStore(Protocol):
    """Persistence operations required by goal use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def create_goal(self, goal: Goal) -> Any:
        """Create a goal."""

    async def get_goal(self, goal_id: str) -> Any | None:
        """Return one goal."""

    async def list_goals(
        self,
        *,
        company_id: str,
        status: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Return goals for one company."""

    async def update_goal_status(
        self,
        goal_id: str,
        *,
        status: str,
        current_value: float | None = None,
    ) -> Any | None:
        """Update one goal status."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
