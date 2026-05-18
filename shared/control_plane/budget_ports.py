"""Ports for control-plane budget persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import AuditEvent, BudgetPeriod, BudgetPolicy, BudgetScope, CompanyContext


class ControlPlaneBudgetStore(Protocol):
    """Persistence operations required by budget use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def create_budget_policy(self, budget: BudgetPolicy) -> Any:
        """Create a budget policy."""

    async def get_budget_policy(self, budget_id: str) -> Any | None:
        """Return one budget policy."""

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
        """Return budget policies for one company."""

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
        """Update one budget policy."""

    async def get_active_budget_policy(
        self,
        *,
        company_id: str,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> Any | None:
        """Return the active policy for a scope/period."""

    async def list_budget_usage(
        self,
        *,
        company_id: str,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return budget usage rows."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
