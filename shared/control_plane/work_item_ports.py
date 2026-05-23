"""Ports for control-plane work-item persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId, WorkItemId

from .models import AuditEvent, CompanyContext, Goal, WorkItem


class ControlPlaneWorkItemStore(Protocol):
    """Persistence operations required by work-item use cases.

    `work_item_id` parameters use the `WorkItemId` `NewType` from
    `shared.core.identifiers` (DDD-007 first adoption). At runtime
    `WorkItemId` is a plain `str`; static type checkers treat it as a
    distinct type so a `GoalId` or raw `str` cannot be passed where a
    `WorkItemId` is expected.
    """

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def get_goal(self, goal_id: str) -> Goal | None:
        """Return one goal for linkage validation."""

    async def create_work_item(self, work_item: WorkItem) -> WorkItem:
        """Create a work item."""

    async def get_work_item(self, work_item_id: WorkItemId) -> WorkItem | None:
        """Return one work item by typed identifier."""

    async def list_work_items(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        priority: str | None = None,
        goal_id: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        """Return work items for one company."""

    async def update_work_item_status(
        self,
        work_item_id: WorkItemId,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> WorkItem | None:
        """Update one work-item status by typed identifier."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
