"""Tests for the dedicated control-plane agent-run store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    CompanyContext,
    Goal,
    WorkItem,
)
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore


@pytest.mark.asyncio
async def test_agent_run_store_owns_run_queries(db_session: AsyncSession) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    goal_store = SqlAlchemyControlPlaneGoalStore(db_session)
    work_item_store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_agent_run_store", name="Wisdoverse Cell")
    )
    goal = await goal_store.create_goal(
        Goal(company_id=company.company_id, title="Ship runtime ledger")
    )
    work_item = await work_item_store.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Run store extraction",
        )
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="requirement-manager",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_agent_run_store",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            output_events=[{"event_type": "agent_run.started"}],
            metadata={"source": "agent-run-store"},
        )
    )

    rows = await run_store.list_agent_runs(
        company_id=company.company_id,
        status=AgentRunStatus.RUNNING.value,
        agent_id="requirement-manager",
        trace_id="trace_agent_run_store",
        goal_id=goal.goal_id,
        work_item_id=work_item.work_item_id,
    )
    fetched = await run_store.get_agent_run(run.run_id)

    assert [row.run_id for row in rows] == [run.run_id]
    assert fetched is not None
    assert fetched.output_events == [{"event_type": "agent_run.started"}]
    assert fetched.metadata == {"source": "agent-run-store"}
    assert not hasattr(fetched, "metadata_json")


@pytest.mark.asyncio
async def test_agent_run_store_updates_status_and_usage(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_agent_run_usage", name="Wisdoverse Cell")
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
        )
    )

    await run_store.add_agent_run_usage(
        run.run_id,
        cost_usd=0.25,
        input_tokens=100,
        output_tokens=40,
    )
    usage = await run_store.add_agent_run_usage(
        run.run_id,
        cost_usd=0.75,
        input_tokens=30,
        output_tokens=20,
    )
    failed = await run_store.update_agent_run_status(
        run.run_id,
        AgentRunStatus.FAILED,
        error_category="network",
        error_message="provider timeout",
        last_successful_step="validated_input",
    )

    assert usage is not None
    assert usage.cost_usd == pytest.approx(1.0)
    assert usage.input_tokens == 130
    assert usage.output_tokens == 60
    assert failed is not None
    assert failed.status == AgentRunStatus.FAILED.value
    assert failed.completed_at is not None
    assert failed.error_category == "network"
    assert failed.last_successful_step == "validated_input"
