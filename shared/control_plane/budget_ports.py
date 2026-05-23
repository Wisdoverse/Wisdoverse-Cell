"""Ports for control-plane budget persistence."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core.identifiers import BudgetPolicyId, CompanyId

from .models import (
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
)


class ControlPlaneBudgetStore(Protocol):
    """Persistence operations required by budget use cases.

    `budget_id` parameters use the `BudgetPolicyId` `NewType` from
    `shared.core.identifiers` (DDD-007 adoption).
    """

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def create_budget_policy(self, budget: BudgetPolicy) -> BudgetPolicy:
        """Create a budget policy."""

    async def get_budget_policy(self, budget_id: BudgetPolicyId) -> BudgetPolicy | None:
        """Return one budget policy by typed identifier."""

    async def list_budget_policies(
        self,
        *,
        company_id: CompanyId,
        scope: BudgetScope | str | None = None,
        scope_id: str | None = None,
        period: BudgetPeriod | str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[BudgetPolicy]:
        """Return budget policies for one company."""

    async def update_budget_policy(
        self,
        budget_id: BudgetPolicyId,
        *,
        limit_usd: float | None = None,
        warning_threshold: float | None = None,
        status: str | None = None,
        model_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetPolicy | None:
        """Update one budget policy by typed identifier."""

    async def get_active_budget_policy(
        self,
        *,
        company_id: CompanyId,
        scope: BudgetScope | str,
        period: BudgetPeriod | str,
        scope_id: str | None = None,
    ) -> BudgetPolicy | None:
        """Return the active policy for a scope/period."""

    async def list_budget_usage(
        self,
        *,
        company_id: CompanyId,
        budget_id: BudgetPolicyId | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetUsage]:
        """Return budget usage rows; optionally scoped to a typed BudgetPolicyId."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
