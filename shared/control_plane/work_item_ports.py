"""Ports for control-plane work-item persistence."""
from __future__ import annotations

from typing import Protocol

from .models import AuditEvent, CompanyContext, Goal, WorkItem


class ControlPlaneWorkItemStore(Protocol):
    """Persistence operations required by work-item use cases."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def get_goal(self, goal_id: str) -> Goal | None:
        """Return one goal for linkage validation."""

    async def create_work_item(self, work_item: WorkItem) -> WorkItem:
        """Create a work item."""

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        """Return one work item."""

    async def list_work_items(
        self,
        *,
        company_id: str,
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
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> WorkItem | None:
        """Update one work-item status."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
