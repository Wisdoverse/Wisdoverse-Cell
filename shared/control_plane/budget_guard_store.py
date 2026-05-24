"""SQLAlchemy adapter for budget guard persistence."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import CompanyId

from .agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from .budget_guard_ports import ControlPlaneBudgetGuardStore
from .budget_store import SqlAlchemyControlPlaneBudgetStore
from .models import AgentRun, AuditEvent, BudgetPeriod, BudgetPolicy, BudgetScope, BudgetUsage


class SqlAlchemyControlPlaneBudgetGuardStore(ControlPlaneBudgetGuardStore):
    """Session-scoped budget guard store."""

    def __init__(self, session: AsyncSession):
        self._runs = SqlAlchemyControlPlaneAgentRunStore(session)
        self._budgets = SqlAlchemyControlPlaneBudgetStore(session)

    async def get_active_budget_policy(
        self,
        *,
        company_id: CompanyId,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicy | None:
        return await self._budgets.get_active_budget_policy(
            company_id=company_id,
            scope=scope,
            period=period,
            scope_id=scope_id,
        )

    async def get_budget_usage_total(self, budget_id: str) -> float:
        return await self._budgets.get_budget_usage_total(budget_id)

    async def record_budget_usage(self, usage: BudgetUsage) -> BudgetUsage:
        return await self._budgets.record_budget_usage(usage)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._budgets.append_audit_event(event)

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AgentRun | None:
        return await self._runs.add_agent_run_usage(
            run_id,
            cost_usd=cost_usd,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
        )
