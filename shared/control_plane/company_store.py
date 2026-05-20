"""SQLAlchemy adapter for control-plane company context persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .company_ports import ControlPlaneCompanyStore
from .models import AuditEvent, CompanyContext
from .store_utils import model_values, now_utc, to_db_value
from .tables import AuditEventTable, CompanyContextTable


class SqlAlchemyControlPlaneCompanyStore(ControlPlaneCompanyStore):
    """Session-scoped control-plane company store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        row = CompanyContextTable(**model_values(company))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        result = await self._session.execute(
            select(CompanyContextTable).where(
                CompanyContextTable.company_id == company_id
            )
        )
        return result.scalar_one_or_none()

    async def list_companies(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[CompanyContextTable]:
        query = select(CompanyContextTable)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    CompanyContextTable.company_id.ilike(pattern),
                    CompanyContextTable.name.ilike(pattern),
                    CompanyContextTable.mission.ilike(pattern),
                )
            )
        result = await self._session.execute(
            query.order_by(CompanyContextTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_company_context(
        self,
        company_id: str,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContextTable | None:
        row = await self.get_company(company_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if mission is not None:
            row.mission = mission
        if metadata is not None:
            row.metadata_json = to_db_value(metadata)
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        if event.idempotency_key:
            existing = await self._get_audit_by_idempotency(
                event.company_id, event.idempotency_key
            )
            if existing is not None:
                return existing

        row = AuditEventTable(**model_values(event))
        self._session.add(row)
        await self._session.flush()
        return row

    async def _get_audit_by_idempotency(
        self, company_id: str, idempotency_key: str
    ) -> AuditEventTable | None:
        result = await self._session.execute(
            select(AuditEventTable).where(
                AuditEventTable.company_id == company_id,
                AuditEventTable.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()
