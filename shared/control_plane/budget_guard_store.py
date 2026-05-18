"""SQLAlchemy adapter for budget guard persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .budget_guard_ports import ControlPlaneBudgetGuardStore
from .models import BudgetPeriod, BudgetScope, BudgetUsage
from .repository import ControlPlaneRepository


class SqlAlchemyControlPlaneBudgetGuardStore(ControlPlaneBudgetGuardStore):
    """Session-scoped budget guard store."""

    def __init__(self, session: AsyncSession):
        self._budgets = ControlPlaneRepository(session)

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

    async def get_budget_usage_total(self, budget_id: str) -> float:
        return await self._budgets.get_budget_usage_total(budget_id)

    async def record_budget_usage(self, usage: BudgetUsage) -> Any:
        return await self._budgets.record_budget_usage(usage)

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Any | None:
        return await self._budgets.add_agent_run_usage(
            run_id,
            cost_usd=cost_usd,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
        )
