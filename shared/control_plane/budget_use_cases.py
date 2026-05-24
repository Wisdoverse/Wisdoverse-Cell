"""Application use cases for control-plane budgets."""

from __future__ import annotations

from typing import Any

from .budget_ports import ControlPlaneBudgetStore
from .domain.budget_policy import (
    BudgetPolicy as BudgetPolicyAggregate,
)
from .domain.budget_policy import (
    BudgetPolicyConflictError,
    BudgetPolicyConflictPolicy,
    budget_policy_status,
)
from .domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
from .models import (
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
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
) -> list[BudgetPolicy]:
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
) -> BudgetPolicy:
    """Return one budget policy in a company or raise not found."""
    policy = await store.get_budget_policy(budget_id)
    if policy is None or policy.company_id != company_id:
        raise BudgetPolicyNotFoundError(budget_id)
    return policy


async def create_budget_policy_with_audit(
    store: ControlPlaneBudgetStore,
    budget: BudgetPolicy,
    *,
    created_by: str,
) -> BudgetPolicy:
    """Create a budget policy and record its audit event."""
    aggregate = BudgetPolicyAggregate.for_creation(budget)
    conflict_policy = BudgetPolicyConflictPolicy()
    await _ensure_company(store, aggregate.record.company_id)
    if conflict_policy.requires_unique_active_policy(aggregate.status):
        await _ensure_no_active_policy_conflict(
            store,
            conflict_policy,
            company_id=aggregate.record.company_id,
            scope=aggregate.record.scope,
            scope_id=aggregate.record.scope_id,
            period=aggregate.record.period,
        )

    created = await store.create_budget_policy(aggregate.record)
    aggregate.record = created
    aggregate.mark_created()
    await append_control_plane_domain_event_audits(
        store,
        aggregate.pull_events(),
        DomainEventAuditContext(actor_type="user", actor_id=created_by),
    )
    return created


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
) -> BudgetPolicy:
    """Update a budget policy and record its audit event."""
    existing = await store.get_budget_policy(budget_id)
    if existing is None or existing.company_id != company_id:
        raise BudgetPolicyNotFoundError(budget_id)

    aggregate = BudgetPolicyAggregate.from_record(existing)
    conflict_policy = BudgetPolicyConflictPolicy()
    if conflict_policy.requires_unique_active_policy(budget_policy_status(status)):
        await _ensure_no_active_policy_conflict(
            store,
            conflict_policy,
            company_id=company_id,
            scope=existing.scope,
            scope_id=existing.scope_id,
            period=existing.period,
            current_budget_id=budget_id,
        )
    aggregate.apply_update(
        limit_usd=limit_usd,
        warning_threshold=warning_threshold,
        status=status,
        model_allowlist=model_allowlist,
        metadata=metadata,
        changed_fields=changed_fields,
    )

    updated = await store.update_budget_policy(
        budget_id,
        limit_usd=aggregate.record.limit_usd if limit_usd is not None else None,
        warning_threshold=(
            aggregate.record.warning_threshold if warning_threshold is not None else None
        ),
        status=aggregate.record.status if status is not None else None,
        model_allowlist=aggregate.record.model_allowlist if model_allowlist is not None else None,
        metadata=aggregate.record.metadata if metadata is not None else None,
    )
    if updated is None:
        raise BudgetPolicyNotFoundError(budget_id)

    aggregate.record = updated
    await append_control_plane_domain_event_audits(
        store,
        aggregate.pull_events(),
        DomainEventAuditContext(actor_type="user", actor_id=actor_id),
    )
    return updated


async def list_budget_usage(
    store: ControlPlaneBudgetStore,
    *,
    company_id: str,
    budget_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 50,
) -> list[BudgetUsage]:
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
    conflict_policy: BudgetPolicyConflictPolicy,
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
    try:
        conflict_policy.ensure_no_active_conflict(
            existing=existing,
            current_budget_id=current_budget_id,
        )
    except BudgetPolicyConflictError as exc:
        raise ActiveBudgetPolicyConflictError(exc.budget_id) from exc
