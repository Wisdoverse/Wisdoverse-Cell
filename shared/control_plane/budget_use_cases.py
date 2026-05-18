"""Application use cases for control-plane budgets."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .budget_ports import ControlPlaneBudgetStore
from .models import (
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
)


class ActiveBudgetPolicyConflictError(Exception):
    """Raised when an active budget policy already exists for a scope/period."""


class BudgetPolicyNotFoundError(Exception):
    """Raised when a budget policy cannot be found in the target company."""


async def list_budget_policies(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    scope: BudgetScope | str | None = None,
    scope_id: str | None = None,
    period: BudgetPeriod | str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List budget policies for one company."""
    return await store.list_budget_policies(
        company_id=company_id,
        scope=scope,
        scope_id=scope_id,
        period=period,
        status=status,
        limit=limit,
    )


async def get_budget_policy(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    budget_id: str,
) -> Any:
    """Return one budget policy in a company or raise not found."""
    row = await store.get_budget_policy(budget_id)
    if row is None or row.company_id != company_id:
        raise BudgetPolicyNotFoundError(budget_id)
    return row


async def create_budget_policy_with_audit(
    store: ControlPlaneBudgetStore,
    budget: BudgetPolicy,
    *,
    created_by: str,
) -> Any:
    """Create a budget policy and record its audit event."""
    await _ensure_company(store, budget.company_id)
    if budget.status == "active":
        await _ensure_no_active_policy_conflict(
            store,
            company_id=budget.company_id,
            scope=budget.scope,
            scope_id=budget.scope_id,
            period=budget.period,
        )

    row = await store.create_budget_policy(budget)
    await store.append_audit_event(
        AuditEvent(
            company_id=budget.company_id,
            action=EventTypes.BUDGET_POLICY_CREATED,
            target_type="budget_policy",
            target_id=row.budget_id,
            actor_type="user",
            actor_id=created_by,
            detail={
                "budget_id": row.budget_id,
                "scope": row.scope,
                "scope_id": row.scope_id,
                "period": row.period,
                "limit_usd": row.limit_usd,
                "warning_threshold": row.warning_threshold,
                "status": row.status,
                "model_allowlist": row.model_allowlist,
            },
        )
    )
    return row


async def update_budget_policy_with_audit(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    budget_id: str,
    limit_usd: float | None = None,
    warning_threshold: float | None = None,
    status: str | None = None,
    model_allowlist: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    actor_id: str,
    changed_fields: list[str],
) -> Any:
    """Update a budget policy and record its audit event."""
    existing = await store.get_budget_policy(budget_id)
    if existing is None or existing.company_id != company_id:
        raise BudgetPolicyNotFoundError(budget_id)

    if status == "active":
        await _ensure_no_active_policy_conflict(
            store,
            company_id=company_id,
            scope=existing.scope,
            scope_id=existing.scope_id,
            period=existing.period,
            current_budget_id=budget_id,
        )

    row = await store.update_budget_policy(
        budget_id,
        limit_usd=limit_usd,
        warning_threshold=warning_threshold,
        status=status,
        model_allowlist=model_allowlist,
        metadata=metadata,
    )
    if row is None:
        raise BudgetPolicyNotFoundError(budget_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.BUDGET_POLICY_UPDATED,
            target_type="budget_policy",
            target_id=row.budget_id,
            actor_type="user",
            actor_id=actor_id,
            detail={
                "budget_id": row.budget_id,
                "scope": row.scope,
                "scope_id": row.scope_id,
                "period": row.period,
                "status": row.status,
                "changed_fields": sorted(changed_fields),
            },
        )
    )
    return row


async def list_budget_usage(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    budget_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 50,
) -> list[Any]:
    """List budget usage for one company."""
    return await store.list_budget_usage(
        company_id=company_id,
        budget_id=budget_id,
        run_id=run_id,
        trace_id=trace_id,
        limit=limit,
    )


async def _ensure_company(store: ControlPlaneBudgetStore, company_id: str) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


async def _ensure_no_active_policy_conflict(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    scope: BudgetScope | str,
    period: BudgetPeriod | str,
    scope_id: str | None,
    current_budget_id: str | None = None,
) -> None:
    existing = await store.get_active_budget_policy(
        company_id=company_id,
        scope=scope,
        scope_id=scope_id,
        period=period,
    )
    if existing is not None and existing.budget_id != current_budget_id:
        raise ActiveBudgetPolicyConflictError(existing.budget_id)
