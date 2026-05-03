"""LLM budget usage EventBus evidence tests."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane import database as control_plane_database
from shared.control_plane.models import BudgetPeriod, BudgetPolicy, BudgetScope, CompanyContext
from shared.control_plane.repository import ControlPlaneRepository
from shared.infra import llm_gateway as llm_gateway_module
from shared.infra.llm_gateway import ControlPlaneBudgetReservation, LLMGateway


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider():
        yield db_session
        await db_session.flush()

    return _provider


@pytest.mark.asyncio
async def test_llm_budget_usage_recording_publishes_event(
    db_session: AsyncSession,
    monkeypatch,
):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_llm_event", name="LLM Event Test")
    )
    budget = await repo.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="agent-a",
            period=BudgetPeriod.DAILY,
            limit_usd=5.0,
        )
    )
    publish_budget = AsyncMock()
    monkeypatch.setattr(
        llm_gateway_module,
        "publish_budget_usage_recorded",
        publish_budget,
    )
    monkeypatch.setattr(
        control_plane_database.control_plane_db_manager,
        "session",
        lambda: _session_provider(db_session)(),
    )
    gateway = LLMGateway(api_key="test-key")

    await gateway._record_control_plane_budget_usage(
        reservation=ControlPlaneBudgetReservation(
            company_id=company.company_id,
            budget_id=budget.budget_id,
        ),
        cost_usd=0.012,
        model="anthropic/claude-sonnet-4-20250514",
        source_agent_id="agent-a",
        input_tokens=100,
        output_tokens=30,
        run_id=None,
        trace_id="trace-llm-budget",
    )

    assert await repo.get_budget_usage_total(budget.budget_id) == pytest.approx(0.012)
    publish_budget.assert_awaited_once()
    publish_kwargs = publish_budget.await_args.kwargs
    assert publish_kwargs["company_id"] == company.company_id
    assert publish_kwargs["budget_id"] == budget.budget_id
    assert publish_kwargs["cost_usd"] == pytest.approx(0.012)
    assert publish_kwargs["source_agent_id"] == "agent-a"
    assert publish_kwargs["input_tokens"] == 100
    assert publish_kwargs["output_tokens"] == 30
    assert publish_kwargs["trace_id"] == "trace-llm-budget"
