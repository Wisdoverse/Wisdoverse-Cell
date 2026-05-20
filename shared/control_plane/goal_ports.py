"""Ports for control-plane goal persistence."""
from __future__ import annotations

from typing import Protocol

from .models import AuditEvent, CompanyContext, Goal


class ControlPlaneGoalStore(Protocol):
    """Persistence operations required by goal use cases."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def create_goal(self, goal: Goal) -> Goal:
        """Create a goal."""

    async def get_goal(self, goal_id: str) -> Goal | None:
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
    ) -> list[Goal]:
        """Return goals for one company."""

    async def update_goal_status(
        self,
        goal_id: str,
        *,
        status: str,
        current_value: float | None = None,
    ) -> Goal | None:
        """Update one goal status."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
