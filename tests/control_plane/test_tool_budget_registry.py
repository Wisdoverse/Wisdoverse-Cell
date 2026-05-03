"""Tool registry budget enforcement against the control-plane ledger."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.approval_gate import ApprovalGate, ApprovalRequiredError
from shared.control_plane.budget_guard import BudgetExceededError
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
)
from shared.control_plane.repository import ControlPlaneRepository
from shared.infra.tool_registry import ToolContext, ToolResult, build_tool


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def _provider():
        yield db_session
        await db_session.flush()

    return _provider


@pytest.mark.asyncio
async def test_expensive_tool_merges_cost_into_agent_run(
    db_session: AsyncSession,
):
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_tool_cost", name="Tool Cost Test")
    )
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace-tool-cost",
        )
    )

    async def handler(_input: dict, _context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data={"ok": True})

    tool = build_tool(
        name="agentforge_run",
        description="Run an AgentForge workflow",
        handler=handler,
        estimated_cost_usd=1.25,
    )

    result = await tool.execute(
        {},
        ToolContext(
            agent_id="dev-agent",
            company_id=company.company_id,
            run_id=run.run_id,
            trace_id="trace-tool-cost",
            control_plane_session_provider=_session_provider(db_session),
        ),
    )

    updated = await repo.get_agent_run(run.run_id)
    assert result.success is True
    assert updated is not None
    assert updated.cost_usd == pytest.approx(1.25)


@pytest.mark.asyncio
async def test_expensive_tool_budget_blocks_before_handler(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.infra.tool_registry.settings.control_plane_tool_budget_enforced",
        True,
    )
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_tool_block", name="Tool Block Test")
    )
    await repo.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=0.5,
        )
    )
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace-tool-block",
        )
    )
    calls = 0

    async def handler(_input: dict, _context: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(success=True)

    tool = build_tool(
        name="expensive_delete",
        description="Expensive destructive tool",
        handler=handler,
        estimated_cost_usd=1.0,
    )

    with pytest.raises(BudgetExceededError, match="budget_exceeded"):
        await tool.execute(
            {},
            ToolContext(
                agent_id="dev-agent",
                company_id=company.company_id,
                run_id=run.run_id,
                control_plane_session_provider=_session_provider(db_session),
            ),
        )

    updated = await repo.get_agent_run(run.run_id)
    assert calls == 0
    assert updated is not None
    assert updated.cost_usd == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_destructive_tool_requires_approved_control_plane_approval(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.infra.tool_registry.settings.control_plane_approval_enforced",
        True,
    )
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_tool_approval", name="Tool Approval Test")
    )
    calls = 0

    async def handler(_input: dict, _context: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(success=True, data={"approved": True})

    tool = build_tool(
        name="agentforge_deploy",
        description="Run a production deployment workflow",
        handler=handler,
        is_destructive=True,
    )
    context = ToolContext(
        agent_id="dev-agent",
        company_id=company.company_id,
        control_plane_session_provider=_session_provider(db_session),
    )

    with pytest.raises(ApprovalRequiredError, match="control_plane_approval_required"):
        await tool.execute({}, context)

    approval = await ApprovalGate(repo).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:dev-agent",
        source_agent_id="dev-agent",
        proposed_action="Run production deployment workflow",
        reason="Operator requested deployment",
        risk="Production behavior may change",
        rollback_note="Cancel workflow or revert deployment",
        affected_resources=["agentforge:workflow", "production"],
    )
    await ApprovalGate(repo).approve(approval.approval_id, resolved_by="human:cto")

    result = await tool.execute(
        {},
        context.model_copy(update={"approval_id": approval.approval_id}),
    )

    assert result.success is True
    assert calls == 1


@pytest.mark.asyncio
async def test_expensive_tool_records_budget_usage_when_allowed(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "shared.infra.tool_registry.settings.control_plane_tool_budget_enforced",
        True,
    )
    repo = ControlPlaneRepository(db_session)
    company = await repo.create_company(
        CompanyContext(company_id="cmp_tool_allowed", name="Tool Allowed Test")
    )
    budget = await repo.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="dev-agent",
            period=BudgetPeriod.DAILY,
            limit_usd=5.0,
        )
    )
    run = await repo.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace-tool-allowed",
        )
    )

    async def handler(_input: dict, _context: ToolContext) -> ToolResult:
        return ToolResult(success=True)

    tool = build_tool(
        name="agentforge_apply",
        description="Apply an AgentForge workflow",
        handler=handler,
        estimated_cost_usd=0.75,
    )

    await tool.execute(
        {},
        ToolContext(
            agent_id="dev-agent",
            company_id=company.company_id,
            run_id=run.run_id,
            trace_id="trace-tool-allowed",
            control_plane_session_provider=_session_provider(db_session),
        ),
    )

    updated = await repo.get_agent_run(run.run_id)
    assert updated is not None
    assert updated.cost_usd == pytest.approx(0.75)
    assert await repo.get_budget_usage_total(budget.budget_id) == pytest.approx(0.75)
