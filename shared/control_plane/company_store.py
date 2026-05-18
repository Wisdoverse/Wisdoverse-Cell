"""SQLAlchemy adapter for control-plane company context persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .company_ports import ControlPlaneCompanyStore
from .models import AuditEvent, CompanyContext
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneCompanyStore(ControlPlaneCompanyStore):
    """Session-scoped control-plane company store."""

    def __init__(self, session: AsyncSession):
        self._companies = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._companies.get_company(company_id)

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._companies.list_companies(search=search, limit=limit)

    async def update_company_context(
        self,
        company_id: str,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        return await self._companies.update_company_context(
            company_id,
            name=name,
            mission=mission,
            metadata=metadata,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._companies.append_audit_event(event)
