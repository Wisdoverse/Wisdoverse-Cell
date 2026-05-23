"""Ports for control-plane goal persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId, GoalId

from .models import AuditEvent, CompanyContext, Goal


class ControlPlaneGoalStore(Protocol):
    """Persistence operations required by goal use cases.

    `goal_id` parameters use the `GoalId` `NewType` from
    `shared.core.identifiers` (DDD-007 adoption). At runtime
    `GoalId` is a plain `str`; static type checkers treat it as a
    distinct type so a `WorkItemId` or raw `str` cannot be passed
    where a `GoalId` is expected.
    """

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def create_goal(self, goal: Goal) -> Goal:
        """Create a goal."""

    async def get_goal(self, goal_id: GoalId) -> Goal | None:
        """Return one goal by typed identifier."""

    async def list_goals(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Goal]:
        """Return goals for one company."""

    async def update_goal_status(
        self,
        goal_id: GoalId,
        *,
        status: str,
        current_value: float | None = None,
    ) -> Goal | None:
        """Update one goal status by typed identifier."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
