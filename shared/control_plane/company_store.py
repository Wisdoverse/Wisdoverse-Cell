"""SQLAlchemy adapter for control-plane company context persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import CompanyId

from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .company_ports import ControlPlaneCompanyStore
from .domain_records import company_record
from .models import AuditEvent, CompanyContext
from .store_utils import model_values, now_utc, to_db_value
from .tables import CompanyContextTable


class SqlAlchemyControlPlaneCompanyStore(ControlPlaneCompanyStore):
    """Session-scoped control-plane company store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        if (company.metadata or {}).get("template_import") is True:
            from sqlalchemy.exc import IntegrityError

            from .company_template_models import CompanyTemplateNameTable
            from .company_template_use_cases import CompanyTemplateNameCollisionError

            try:
                async with self._session.begin_nested():
                    self._session.add(CompanyTemplateNameTable(
                        normalized_name=company.name.strip().casefold(), company_id=company.company_id))
                    await self._session.flush()
            except IntegrityError as exc:
                raise CompanyTemplateNameCollisionError("company_template_name_collision") from exc
        row = CompanyContextTable(**model_values(company))
        self._session.add(row)
        await self._session.flush()
        return company_record(row)

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        row = await self._get_company_row(company_id)
        return company_record(row) if row is not None else None

    async def _get_company_row(self, company_id: CompanyId) -> CompanyContextTable | None:
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
    ) -> list[CompanyContext]:
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
        return [company_record(row) for row in result.scalars().all()]

    async def update_company_context(
        self,
        company_id: CompanyId,
        *,
        name: str | None = None,
        mission: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CompanyContext | None:
        row = await self._get_company_row(company_id)
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
        return company_record(row)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._audits.append_audit_event(event)
