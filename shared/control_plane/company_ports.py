"""Ports for control-plane company context persistence."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core.identifiers import CompanyId

from .models import AuditEvent, CompanyContext


class ControlPlaneCompanyStore(Protocol):
    """Persistence operations required by company context use cases.

    `company_id` parameters use the `CompanyId` `NewType` from
    `shared.core.identifiers` (DDD-007 adoption).
    """

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return one company context by typed identifier."""

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CompanyContext]:
        """Return company contexts."""

    async def update_company_context(
        self,
        company_id: CompanyId,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContext | None:
        """Update one company context by typed identifier."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
