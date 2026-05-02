"""Shared budget guard for expensive agent and LLM work."""

from dataclasses import dataclass

from .models import BudgetPeriod, BudgetScope, BudgetUsage
from .repository import ControlPlaneRepository


class BudgetExceededError(PermissionError):
    """Raised when a planned action exceeds the active budget policy."""


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    budget_id: str | None
    current_cost_usd: float
    estimated_cost_usd: float
    estimated_total_usd: float
    limit_usd: float | None
    reason: str = ""


class BudgetGuard:
    """Checks and records budget usage against active budget policies."""

    def __init__(self, repo: ControlPlaneRepository):
        self._repo = repo

    async def check(
        self,
        *,
        company_id: str,
        scope: BudgetScope,
        period: BudgetPeriod,
        estimated_cost_usd: float,
        scope_id: str | None = None,
        model: str | None = None,
    ) -> BudgetDecision:
        policy = await self._repo.get_active_budget_policy(
            company_id=company_id,
            scope=scope,
            period=period,
            scope_id=scope_id,
        )
        if policy is None:
            return BudgetDecision(
                allowed=True,
                budget_id=None,
                current_cost_usd=0.0,
                estimated_cost_usd=estimated_cost_usd,
                estimated_total_usd=estimated_cost_usd,
                limit_usd=None,
                reason="no_active_policy",
            )

        if model and policy.model_allowlist and model not in policy.model_allowlist:
            return BudgetDecision(
                allowed=False,
                budget_id=policy.budget_id,
                current_cost_usd=await self._repo.get_budget_usage_total(policy.budget_id),
                estimated_cost_usd=estimated_cost_usd,
                estimated_total_usd=estimated_cost_usd,
                limit_usd=policy.limit_usd,
                reason="model_not_allowed",
            )

        current = await self._repo.get_budget_usage_total(policy.budget_id)
        estimated_total = current + estimated_cost_usd
        allowed = estimated_total <= policy.limit_usd
        return BudgetDecision(
            allowed=allowed,
            budget_id=policy.budget_id,
            current_cost_usd=current,
            estimated_cost_usd=estimated_cost_usd,
            estimated_total_usd=estimated_total,
            limit_usd=policy.limit_usd,
            reason="" if allowed else "budget_exceeded",
        )

    async def ensure_allowed(self, **kwargs) -> BudgetDecision:
        decision = await self.check(**kwargs)
        if not decision.allowed:
            raise BudgetExceededError(decision.reason)
        return decision

    async def record_usage(
        self,
        *,
        company_id: str,
        budget_id: str,
        cost_usd: float,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        run_id: str | None = None,
        trace_id: str | None = None,
    ):
        return await self._repo.record_budget_usage(
            BudgetUsage(
                company_id=company_id,
                budget_id=budget_id,
                cost_usd=cost_usd,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                run_id=run_id,
                trace_id=trace_id,
            )
        )
