"""Tests for shared budget enforcement."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.budget_guard import BudgetExceededError, BudgetGuard
from shared.control_plane.budget_guard_store import SqlAlchemyControlPlaneBudgetGuardStore
from shared.control_plane.budget_store import SqlAlchemyControlPlaneBudgetStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.models import (
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
)


@pytest.mark.asyncio
async def test_budget_guard_allows_when_no_policy_exists(db_session: AsyncSession):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    guard = BudgetGuard(guard_store)

    decision = await guard.check(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.DAILY,
        estimated_cost_usd=100,
    )

    assert decision.allowed is True
    assert decision.reason == "no_active_policy"


@pytest.mark.asyncio
async def test_budget_guard_blocks_when_estimate_exceeds_limit(db_session: AsyncSession):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    budgets = SqlAlchemyControlPlaneBudgetStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    policy = await budgets.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=10,
        )
    )
    guard = BudgetGuard(guard_store)
    await guard.record_usage(
        company_id=company.company_id,
        budget_id=policy.budget_id,
        cost_usd=8,
        model="claude-sonnet-4-20250514",
    )

    decision = await guard.check(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.DAILY,
        estimated_cost_usd=3,
    )

    assert decision.allowed is False
    assert decision.reason == "budget_exceeded"
    assert decision.current_cost_usd == pytest.approx(8)
    assert decision.estimated_total_usd == pytest.approx(11)

    with pytest.raises(BudgetExceededError):
        await guard.ensure_allowed(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            estimated_cost_usd=3,
        )


@pytest.mark.asyncio
async def test_budget_guard_enforces_model_allowlist(db_session: AsyncSession):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    budgets = SqlAlchemyControlPlaneBudgetStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    await budgets.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="requirement-manager",
            period=BudgetPeriod.MONTHLY,
            limit_usd=100,
            model_allowlist=["claude-haiku-4-5-20251001"],
        )
    )
    guard = BudgetGuard(guard_store)

    decision = await guard.check(
        company_id=company.company_id,
        scope=BudgetScope.AGENT,
        scope_id="requirement-manager",
        period=BudgetPeriod.MONTHLY,
        estimated_cost_usd=1,
        model="claude-sonnet-4-20250514",
    )

    assert decision.allowed is False
    assert decision.reason == "model_not_allowed"
