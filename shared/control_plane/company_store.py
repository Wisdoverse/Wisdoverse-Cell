"""SQLAlchemy adapter for control-plane company context persistence."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .company_ports import ControlPlaneCompanyStore
from .models import AuditEvent, CompanyContext
from .tables import AuditEventTable, CompanyContextTable


def _now() -> datetime:
    return datetime.now(UTC)


def _to_db_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_to_db_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_db_value(item) for key, item in value.items()}
    return value


def _model_values(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump(mode="python")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        db_key = "metadata_json" if key == "metadata" else key
        normalized[db_key] = _to_db_value(value)
    return normalized


class SqlAlchemyControlPlaneCompanyStore(ControlPlaneCompanyStore):
    """Session-scoped control-plane company store."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        row = CompanyContextTable(**_model_values(company))
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
            row.metadata_json = _to_db_value(metadata)
        row.updated_at = _now()
        await self._session.flush()
        return row

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        row = AuditEventTable(**_model_values(event))
        self._session.add(row)
        await self._session.flush()
        return row
