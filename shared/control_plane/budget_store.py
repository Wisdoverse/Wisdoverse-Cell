"""SQLAlchemy adapter for control-plane budget persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .budget_ports import ControlPlaneBudgetStore
from .models import (
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
)
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneBudgetStore(ControlPlaneBudgetStore):
    """Session-scoped control-plane budget store."""

    def __init__(self, session: AsyncSession):
        self._budgets = ControlPlaneRepository(session)

    async def create_company(self, company: CompanyContext) -> Any:
        return await self._budgets.create_company(company)

    async def get_company(self, company_id: str) -> Any | None:
        return await self._budgets.get_company(company_id)

    async def create_budget_policy(self, budget: BudgetPolicy) -> Any:
        return await self._budgets.create_budget_policy(budget)

    async def get_budget_policy(self, budget_id: str) -> Any | None:
        return await self._budgets.get_budget_policy(budget_id)

    async def list_budget_policies(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str | None = None,
        scope_id: str | None = None,
        period: BudgetPeriod | str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await self._budgets.list_budget_policies(
            company_id=company_id,
            scope=scope,
            scope_id=scope_id,
            period=period,
            status=status,
            limit=limit,
        )

    async def update_budget_policy(
        self,
        budget_id: str,
        *,
        limit_usd: float | None = None,
        warning_threshold: float | None = None,
        status: str | None = None,
        model_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        return await self._budgets.update_budget_policy(
            budget_id,
            limit_usd=limit_usd,
            warning_threshold=warning_threshold,
            status=status,
            model_allowlist=model_allowlist,
            metadata=metadata,
        )

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> Any | None:
        return await self._budgets.get_active_budget_policy(
            company_id=company_id,
            scope=scope,
            period=period,
            scope_id=scope_id,
        )

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        return await self._budgets.list_budget_usage(
            company_id=company_id,
            budget_id=budget_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )

    async def append_audit_event(self, event: AuditEvent) -> Any:
        return await self._budgets.append_audit_event(event)
