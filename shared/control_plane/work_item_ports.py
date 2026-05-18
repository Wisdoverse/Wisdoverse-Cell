"""Ports for control-plane work-item persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, CompanyContext, WorkItem


class ControlPlaneWorkItemStore(Protocol):
    """Persistence operations required by work-item use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def get_goal(self, goal_id: str) -> Any | None:
        """Return one goal for linkage validation."""

    async def create_work_item(self, work_item: WorkItem) -> Any:
        """Create a work item."""

    async def get_work_item(self, work_item_id: str) -> Any | None:
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
    ) -> list[Any]:
        """Return work items for one company."""

    async def update_work_item_status(
        self,
        work_item_id: str,
        *,
        status: str,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> Any | None:
        """Update one work-item status."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
