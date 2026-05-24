"""Tests for shared budget enforcement."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
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
from shared.schemas.event import EventTypes


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


@pytest.mark.asyncio
async def test_budget_guard_rejects_negative_estimates_and_usage(
    db_session: AsyncSession,
):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await companies.create_company(CompanyContext(name="Wisdoverse Cell"))
    guard = BudgetGuard(guard_store)

    with pytest.raises(ValueError, match="non-negative"):
        await guard.check(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            estimated_cost_usd=-0.01,
        )

    with pytest.raises(ValueError, match="non-negative"):
        await guard.record_usage(
            company_id=company.company_id,
            budget_id="bud_test",
            cost_usd=-0.01,
            model="claude-sonnet-4-20250514",
        )


@pytest.mark.asyncio
async def test_budget_guard_records_usage_domain_event_audit(db_session: AsyncSession):
    companies = SqlAlchemyControlPlaneCompanyStore(db_session)
    budgets = SqlAlchemyControlPlaneBudgetStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await companies.create_company(
        CompanyContext(company_id="cmp_budget_usage_domain", name="Budget Usage")
    )
    policy = await budgets.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=10,
        )
    )
    guard = BudgetGuard(guard_store)

    usage = await guard.record_usage(
        company_id=company.company_id,
        budget_id=policy.budget_id,
        cost_usd=0.42,
        model="  tool:agentforge_apply  ",
        input_tokens=10,
        output_tokens=5,
        run_id="run_budget_usage_domain",
        trace_id="trace_budget_usage_domain",
    )
    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id=company.company_id,
        target_type="budget_usage",
    )

    assert usage.model == "tool:agentforge_apply"
    assert len(audits) == 1
    assert audits[0].action == EventTypes.BUDGET_USAGE_RECORDED
    assert audits[0].trace_id == "trace_budget_usage_domain"
    assert audits[0].run_id == "run_budget_usage_domain"
    assert audits[0].detail["domain_event"] == "BudgetUsageRecorded"
    assert audits[0].detail["usage_id"] == usage.usage_id
    assert audits[0].detail["cost_usd"] == pytest.approx(0.42)
    assert audits[0].detail["input_tokens"] == 10
    assert audits[0].detail["output_tokens"] == 5
