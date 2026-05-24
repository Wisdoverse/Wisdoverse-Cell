"""Tests for dedicated control-plane budget stores."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.budget_guard_store import SqlAlchemyControlPlaneBudgetGuardStore
from shared.control_plane.budget_store import SqlAlchemyControlPlaneBudgetStore
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    AuditEvent,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
)


@pytest.mark.asyncio
async def test_budget_store_owns_policy_and_usage_queries(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneBudgetStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_budget_store", name="Wisdoverse Cell")
    )
    policy = await store.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.COMPANY,
            period=BudgetPeriod.DAILY,
            limit_usd=25,
            model_allowlist=["claude-sonnet-4-20250514"],
            metadata={"source": "budget-store"},
        )
    )
    await store.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="qa-agent",
            period=BudgetPeriod.MONTHLY,
            limit_usd=100,
            status="paused",
        )
    )
    first_usage = await store.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=policy.budget_id,
            cost_usd=1.25,
            model="  claude-sonnet-4-20250514  ",
            input_tokens=100,
            output_tokens=50,
            trace_id="trace_budget_store",
        )
    )
    await store.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=policy.budget_id,
            cost_usd=0.75,
            model="claude-sonnet-4-20250514",
            input_tokens=20,
            output_tokens=30,
            trace_id="trace_budget_store_other",
        )
    )

    listed = await store.list_budget_policies(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.DAILY,
        status="active",
    )
    active = await store.get_active_budget_policy(
        company_id=company.company_id,
        scope=BudgetScope.COMPANY,
        period=BudgetPeriod.DAILY,
    )
    updated = await store.update_budget_policy(
        policy.budget_id,
        limit_usd=30,
        warning_threshold=0.7,
        model_allowlist=["claude-opus-4-20250514"],
        metadata={"source": "budget-store-updated"},
    )
    usage_rows = await store.list_budget_usage(
        company_id=company.company_id,
        budget_id=policy.budget_id,
        trace_id="trace_budget_store",
    )
    total = await store.get_budget_usage_total(policy.budget_id)

    assert [row.budget_id for row in listed] == [policy.budget_id]
    assert active is not None
    assert active.budget_id == policy.budget_id
    assert updated is not None
    assert updated.limit_usd == 30
    assert updated.warning_threshold == 0.7
    assert updated.model_allowlist == ["claude-opus-4-20250514"]
    assert updated.metadata == {"source": "budget-store-updated"}
    assert not hasattr(updated, "metadata_json")
    assert first_usage.model == "claude-sonnet-4-20250514"
    assert [row.usage_id for row in usage_rows] == [first_usage.usage_id]
    assert total == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_budget_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneBudgetStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_budget_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="budget_policy.created",
        target_type="budget_policy",
        target_id="bud_001",
        idempotency_key="bud_001:created",
        detail={"source": "budget-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)

    assert first.audit_event_id == second.audit_event_id


@pytest.mark.asyncio
async def test_budget_guard_store_uses_budget_and_agent_run_stores(
    db_session: AsyncSession,
) -> None:
    budget_store = SqlAlchemyControlPlaneBudgetStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    guard_store = SqlAlchemyControlPlaneBudgetGuardStore(db_session)
    company = await budget_store.create_company(
        CompanyContext(company_id="cmp_budget_guard_store", name="Wisdoverse Cell")
    )
    policy = await budget_store.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=20,
        )
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
        )
    )

    active = await guard_store.get_active_budget_policy(
        company_id=company.company_id,
        scope=BudgetScope.AGENT,
        scope_id="dev-agent",
        period=BudgetPeriod.DAILY,
    )
    usage = await guard_store.record_budget_usage(
        BudgetUsage(
            company_id=company.company_id,
            budget_id=policy.budget_id,
            cost_usd=1.5,
            model="claude-sonnet-4-20250514",
            run_id=run.run_id,
        )
    )
    total = await guard_store.get_budget_usage_total(policy.budget_id)
    updated_run = await guard_store.add_agent_run_usage(
        run.run_id,
        cost_usd=1.5,
        input_tokens=100,
        output_tokens=50,
    )

    assert active is not None
    assert active.budget_id == policy.budget_id
    assert usage.budget_id == policy.budget_id
    assert total == pytest.approx(1.5)
    assert updated_run is not None
    assert updated_run.cost_usd == pytest.approx(1.5)
    assert updated_run.input_tokens == 100
    assert updated_run.output_tokens == 50
