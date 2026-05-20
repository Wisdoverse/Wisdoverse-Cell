"""SQLAlchemy adapter for control-plane budget persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .budget_ports import ControlPlaneBudgetStore
from .company_store import SqlAlchemyControlPlaneCompanyStore
from .models import (
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
)
from .store_utils import model_values, now_utc, to_db_value
from .tables import (
    AuditEventTable,
    BudgetPolicyTable,
    BudgetUsageTable,
    CompanyContextTable,
)


class SqlAlchemyControlPlaneBudgetStore(ControlPlaneBudgetStore):
    """Session-scoped control-plane budget store."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._companies = SqlAlchemyControlPlaneCompanyStore(session)

    async def create_company(self, company: CompanyContext) -> CompanyContextTable:
        return await self._companies.create_company(company)

    async def get_company(self, company_id: str) -> CompanyContextTable | None:
        return await self._companies.get_company(company_id)

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicyTable:
        row = BudgetPolicyTable(**model_values(budget))
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_budget_policy(self, budget_id: str) -> BudgetPolicyTable | None:
        result = await self._session.execute(
            select(BudgetPolicyTable).where(BudgetPolicyTable.budget_id == budget_id)
        )
        return result.scalar_one_or_none()

    async def list_budget_policies(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str | None = None,
        scope_id: str | None = None,
        period: BudgetPeriod | str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[BudgetPolicyTable]:
        query = select(BudgetPolicyTable).where(
            BudgetPolicyTable.company_id == company_id
        )
        if scope:
            query = query.where(BudgetPolicyTable.scope == to_db_value(scope))
        if scope_id:
            query = query.where(BudgetPolicyTable.scope_id == scope_id)
        if period:
            query = query.where(BudgetPolicyTable.period == to_db_value(period))
        if status:
            query = query.where(BudgetPolicyTable.status == status)
        result = await self._session.execute(
            query.order_by(BudgetPolicyTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_budget_policy(
        self,
        budget_id: str,
        *,
        limit_usd: float | None = None,
        warning_threshold: float | None = None,
        status: str | None = None,
        model_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetPolicyTable | None:
        row = await self.get_budget_policy(budget_id)
        if row is None:
            return None
        if limit_usd is not None:
            row.limit_usd = limit_usd
        if warning_threshold is not None:
            row.warning_threshold = warning_threshold
        if status is not None:
            row.status = status
        if model_allowlist is not None:
            row.model_allowlist = to_db_value(model_allowlist)
        if metadata is not None:
            row.metadata_json = to_db_value(metadata)
        row.updated_at = now_utc()
        await self._session.flush()
        return row

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicyTable | None:
        query = select(BudgetPolicyTable).where(
            BudgetPolicyTable.company_id == company_id,
            BudgetPolicyTable.scope == to_db_value(scope),
            BudgetPolicyTable.period == to_db_value(period),
            BudgetPolicyTable.status == "active",
        )
        if scope_id is None:
            query = query.where(BudgetPolicyTable.scope_id.is_(None))
        else:
            query = query.where(BudgetPolicyTable.scope_id == scope_id)

        result = await self._session.execute(
            query.order_by(BudgetPolicyTable.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def record_budget_usage(self, usage: BudgetUsage) -> BudgetUsageTable:
        row = BudgetUsageTable(**model_values(usage))
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsageTable]:
        query = select(BudgetUsageTable).where(BudgetUsageTable.company_id == company_id)
        if budget_id:
            query = query.where(BudgetUsageTable.budget_id == budget_id)
        if run_id:
            query = query.where(BudgetUsageTable.run_id == run_id)
        if trace_id:
            query = query.where(BudgetUsageTable.trace_id == trace_id)
        result = await self._session.execute(
            query.order_by(BudgetUsageTable.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_budget_usage_total(self, budget_id: str) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(BudgetUsageTable.cost_usd), 0.0)).where(
                BudgetUsageTable.budget_id == budget_id
            )
        )
        return float(result.scalar_one() or 0.0)

    async def append_audit_event(self, event: AuditEvent) -> AuditEventTable:
        return await self._companies.append_audit_event(event)
