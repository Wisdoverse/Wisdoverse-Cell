"""Ports for budget guard persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import CompanyId

from .models import AgentRun, BudgetPeriod, BudgetPolicy, BudgetScope, BudgetUsage


class ControlPlaneBudgetGuardStore(Protocol):
    """Persistence operations required by budget enforcement."""

    async def get_active_budget_policy(
        self,
        *,
        company_id: CompanyId,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicy | None:
        """Return the active budget policy for a scope/period."""

    async def get_budget_usage_total(self, budget_id: str) -> float:
        """Return the recorded spend for a budget policy."""

    async def record_budget_usage(self, usage: BudgetUsage) -> BudgetUsage:
        """Record one budget usage row."""

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> AgentRun | None:
        """Add usage metrics to an agent run."""
