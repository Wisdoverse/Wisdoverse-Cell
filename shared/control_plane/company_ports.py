"""Ports for control-plane company context persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, CompanyContext


class ControlPlaneCompanyStore(Protocol):
    """Persistence operations required by company context use cases."""

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a company context."""

    async def get_company(self, company_id: str) -> CompanyContext | None:
        """Return one company context."""

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CompanyContext]:
        """Return company contexts."""

    async def update_company_context(
        self,
        company_id: str,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContext | None:
        """Update one company context."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
