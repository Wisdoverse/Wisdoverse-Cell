"""Ports for budget guard persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import BudgetPeriod, BudgetScope, BudgetUsage


class ControlPlaneBudgetGuardStore(Protocol):
    """Persistence operations required by budget enforcement."""

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> Any | None:
        """Return the active budget policy for a scope/period."""

    async def get_budget_usage_total(self, budget_id: str) -> float:
        """Return the recorded spend for a budget policy."""

    async def record_budget_usage(self, usage: BudgetUsage) -> Any:
        """Record one budget usage row."""

    async def add_agent_run_usage(
        self,
        run_id: str,
        *,
        cost_usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Any | None:
        """Add usage metrics to an agent run."""
