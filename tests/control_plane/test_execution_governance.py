"""Execution governance persistence and runner contract tests.

SQLite tests cover durable local invariants. The optional PostgreSQL test uses
an isolated generated schema because SQLite does not implement row locking.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.approval_gate import ApprovalGate
from shared.control_plane.domain.execution_policy import ExecutionDenied
from shared.control_plane.domain.lifecycle.agent_run_lifecycle import start_agent_wakeup_run
from shared.control_plane.execution_models import (
    ExecutionLeaseTable,
    ExecutionReservationTable,
)
from shared.control_plane.execution_ports import ExecutionTicket
from shared.control_plane.execution_store import SqlAlchemyExecutionGovernanceStore
from shared.control_plane.models import (
    AgentRole,
    ApprovalStatus,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    BudgetUsage,
    CompanyContext,
    WorkItem,
    WorkItemStatus,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import control_plane_metadata
from shared.core.identifiers import AgentRoleId, AgentRunId, BudgetPolicyId, CompanyId


@pytest_asyncio.fixture
async def execution_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(control_plane_metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@asynccontextmanager
async def _postgres_schema_factory(
    prefix: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL concurrency tests")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must use PostgreSQL for row-lock coverage")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = f"{prefix}_{uuid4().hex}"
    root_engine = create_async_engine(url)
    async with root_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
        yield async_sessionmaker(scoped_engine, expire_on_commit=False)
    finally:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.drop_all)
        async with root_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


async def _seed_agent(
    session: AsyncSession,
    *,
    company_id: str,
    agent_id: str,
    command: list[str],
    permissions: list[str] | None = None,
    ceiling: float = 0,
    approval_required: bool = False,
) -> tuple[AgentRole, WorkItem | None]:
    stores = ControlPlaneStores(session)
    if await stores.companies.get_company(CompanyId(company_id)) is None:
        await stores.companies.create_company(
            CompanyContext(company_id=company_id, name=f"Company {company_id}")
        )
    agent = await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company_id,
            agent_id=agent_id,
            display_name="Governance Test Agent",
            adapter_type="process",
            permissions=permissions
            if permissions is not None
            else ["work.execute", "adapter:process", "tool:wakeup"],
            adapter_config={
                "command": command,
                "timeout_sec": 10,
                "max_cost_usd": ceiling,
            },
        )
    )
    work_item = None
    if approval_required:
        work_item = await stores.work_items.create_work_item(
            WorkItem(
                company_id=company_id,
                title="Sensitive work item",
                status=WorkItemStatus.READY,
                owner_agent_id=agent_id,
                approval_required=True,
            )
        )
    await session.flush()
    return agent, work_item


def _enable_process(monkeypatch: pytest.MonkeyPatch, agent_id: str) -> None:
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_enabled",
        True,
    )
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_allowlist",
        f"process:{agent_id}",
    )


def _append_marker_command(marker: str) -> list[str]:
    source = (
        "import json,sys; json.load(sys.stdin); "
        f"open({marker!r}, 'a', encoding='utf-8').write('effect\\n'); print('ok')"
    )
    return [sys.executable, "-c", source]


@pytest.mark.asyncio
async def test_bound_approval_survives_session_restart_and_allows_same_intent(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    company_id = "cmp_exec_approval_restart"
    agent_id = "approval-runner"
    marker = str(tmp_path / "effects.txt")
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        agent, work = await _seed_agent(
            session,
            company_id=company_id,
            agent_id=agent_id,
            command=_append_marker_command(marker),
            approval_required=True,
        )
        assert work is not None
        runner = ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations)
        with pytest.raises(AgentWakeupError, match="execution_approval_required"):
            await runner.wake(
                agent,
                input_payload={"task": "publish report"},
                actor_id="human:operator",
                work_item_id=work.work_item_id,
                idempotency_key="approval-restart-key",
            )

    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        approvals = await stores.approvals.list_approvals(company_id=CompanyId(company_id))
        assert len(approvals) == 1
        approval = approvals[0]
        assert approval.status == ApprovalStatus.PENDING.value
        assert approval.metadata["execution_intent_hash"]
        await ApprovalGate(stores.approvals).approve(
            approval.approval_id,
            resolved_by="human:board",
        )
        await session.commit()

    async with execution_session_factory() as session:
        reloaded_agent = await ControlPlaneStores(session).agent_registry.get_agent_role(
            company_id=CompanyId(company_id),
            agent_id=AgentRoleId(agent_id),
        )
        assert reloaded_agent is not None
        assert work is not None
        result = await ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations).wake(
            reloaded_agent,
            input_payload={"task": "publish report"},
            actor_id="human:operator",
            work_item_id=work.work_item_id,
            idempotency_key="approval-restart-key",
        )
        assert result.output["status"] == "ok"

    with open(marker, encoding="utf-8") as marker_file:
        assert marker_file.read().splitlines() == ["effect"]


@pytest.mark.asyncio
async def test_approved_intent_does_not_authorize_changed_adapter_configuration(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    company_id = "cmp_exec_approval_changed"
    agent_id = "changed-config-runner"
    marker = str(tmp_path / "effects.txt")
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        agent, work = await _seed_agent(
            session,
            company_id=company_id,
            agent_id=agent_id,
            command=_append_marker_command(marker),
            approval_required=True,
        )
        assert work is not None
        runner = ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations)
        with pytest.raises(AgentWakeupError, match="execution_approval_required"):
            await runner.wake(
                agent,
                input_payload={"task": "publish report"},
                actor_id="human:operator",
                work_item_id=work.work_item_id,
                idempotency_key="approval-config-key",
            )
        approvals = await ControlPlaneStores(session).approvals.list_approvals(
            company_id=CompanyId(company_id)
        )
        await ApprovalGate(ControlPlaneStores(session).approvals).approve(
            approvals[0].approval_id,
            resolved_by="human:board",
        )
        await session.commit()

    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        await stores.agent_registry.update_agent_role(
            company_id=CompanyId(company_id),
            agent_id=AgentRoleId(agent_id),
            values={
                "adapter_config": {
                    "command": _append_marker_command(marker),
                    "timeout_sec": 10,
                    "max_cost_usd": 0.1,
                }
            },
        )
        changed_agent = await stores.agent_registry.get_agent_role(
            company_id=CompanyId(company_id),
            agent_id=AgentRoleId(agent_id),
        )
        assert changed_agent is not None
        with pytest.raises(AgentWakeupError, match="execution_approval_required"):
            await ControlPlaneAgentRunner(stores.agent_operations).wake(
                changed_agent,
                input_payload={"task": "publish report"},
                actor_id="human:operator",
                work_item_id=work.work_item_id,
                idempotency_key="approval-config-key",
            )
        approvals = await stores.approvals.list_approvals(company_id=CompanyId(company_id))
        assert sorted(approval.status for approval in approvals) == [
            ApprovalStatus.APPROVED.value,
            ApprovalStatus.PENDING.value,
        ]
        runs = await stores.agent_runs.list_agent_runs(
            company_id=CompanyId(company_id), agent_id=agent_id
        )
        assert runs == []

    assert not os.path.exists(marker)


@pytest.mark.asyncio
async def test_denied_permission_does_not_invoke_external_executor(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    company_id = "cmp_exec_denied"
    agent_id = "denied-runner"
    marker = str(tmp_path / "effects.txt")
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        agent, _ = await _seed_agent(
            session,
            company_id=CompanyId(company_id),
            agent_id=agent_id,
            command=_append_marker_command(marker),
            permissions=[],
        )
        runner = ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations)
        with pytest.raises(AgentWakeupError, match="execution_permission_denied"):
            await runner.wake(agent, input_payload={"task": "run"})
        runs = await ControlPlaneStores(session).agent_runs.list_agent_runs(
            company_id=CompanyId(company_id),
            agent_id=agent_id,
        )
        assert runs == []

    assert not os.path.exists(marker)


@pytest.mark.asyncio
async def test_duplicate_execution_replays_one_effect_and_changed_intent_conflicts(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    company_id = "cmp_exec_idempotent"
    agent_id = "idempotent-runner"
    marker = str(tmp_path / "effects.txt")
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        agent, _ = await _seed_agent(
            session,
            company_id=CompanyId(company_id),
            agent_id=agent_id,
            command=_append_marker_command(marker),
        )
        runner = ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations)
        first = await runner.wake(
            agent,
            input_payload={"task": "same"},
            actor_id="human:operator",
            idempotency_key="same-execution-key",
        )
        duplicate = await runner.wake(
            agent,
            input_payload={"task": "same"},
            actor_id="human:operator",
            idempotency_key="same-execution-key",
        )
        assert duplicate.run_id == first.run_id
        assert duplicate.output == first.output
        with pytest.raises(AgentWakeupError, match="idempotency_key_conflict"):
            await runner.wake(
                agent,
                input_payload={"task": "changed"},
                actor_id="human:operator",
                idempotency_key="same-execution-key",
            )
        runs = await ControlPlaneStores(session).agent_runs.list_agent_runs(
            company_id=CompanyId(company_id),
            agent_id=agent_id,
        )
        assert len(runs) == 1

    with open(marker, encoding="utf-8") as marker_file:
        assert marker_file.read().splitlines() == ["effect"]


@pytest.mark.asyncio
async def test_failed_attempt_is_charged_the_reserved_cost_ceiling(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = "cmp_exec_failed_charge"
    agent_id = "failure-charge-runner"
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        await stores.companies.create_company(
            CompanyContext(company_id=company_id, name="Failed Charge")
        )
        policy = await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.DAILY,
                limit_usd=1.0,
            )
        )
        agent, _ = await _seed_agent(
            session,
            company_id=CompanyId(company_id),
            agent_id=agent_id,
            command=[sys.executable, "-c", "raise SystemExit(7)"],
            ceiling=0.3,
        )
        assert policy.budget_id
        runner = ControlPlaneAgentRunner(stores.agent_operations)
        with pytest.raises(AgentWakeupError, match="local_adapter_failed"):
            await runner.wake(agent, input_payload={"task": "fail"})
        usage = await stores.budgets.list_budget_usage(
            company_id=CompanyId(company_id),
            budget_id=BudgetPolicyId(policy.budget_id),
        )
        assert len(usage) == 1
        assert usage[0].cost_usd == pytest.approx(0.3)
        assert usage[0].metadata["failed_attempt"] is True
        assert usage[0].metadata["charged_ceiling"] is True


@pytest.mark.asyncio
async def test_http_executor_overspend_is_charged_and_run_fails(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = "cmp_exec_http_overspend"
    agent_id = "http-overspend-runner"
    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        await stores.companies.create_company(
            CompanyContext(company_id=company_id, name="HTTP Overspend")
        )
        await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.DAILY,
                limit_usd=1.0,
            )
        )
        agent = await stores.agent_registry.create_agent_role(
            AgentRole(
                company_id=company_id,
                agent_id=agent_id,
                display_name="HTTP Overspend Runner",
                adapter_type="http",
                permissions=["work.execute", "adapter:http", "tool:wakeup"],
                adapter_config={
                    "base_url": "http://agent.test",
                    "contract_version": "1.0",
                    "max_cost_usd": 0.1,
                },
            )
        )

        async def report_http_result(_runner, _config, _request):
            return {
                "status": "ok",
                "adapter": "http",
                "cost_usd": 0.2,
                "summary": "completed but exceeded the declared ceiling",
                "response": {"done": True},
                "artifact_references": [],
            }

        monkeypatch.setattr(ControlPlaneAgentRunner, "_execute_http", report_http_result)
        runner = ControlPlaneAgentRunner(stores.agent_operations)
        with pytest.raises(AgentWakeupError, match="executor_cost_ceiling_exceeded") as failure:
            await runner.wake(agent, input_payload={"task": "run within ceiling"})

        runs = await stores.agent_operations.list_agent_runs(
            company_id=CompanyId(company_id), agent_id=agent_id
        )
        assert len(runs) == 1
        assert runs[0].status == "failed"
        usage = await stores.agent_operations.list_budget_usage(
            company_id=CompanyId(company_id), run_id=runs[0].run_id
        )
        assert len(usage) == 1
        assert usage[0].cost_usd == pytest.approx(0.2)
        assert usage[0].metadata["failed_attempt"] is True
        assert failure.value.error_category == "executor_contract"


@pytest.mark.asyncio
async def test_uncertain_http_handoff_holds_reservation_until_recovery_then_allows_retry(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = "cmp_exec_http_uncertain"
    agent_id = "http-uncertain-runner"
    work_item_id = None
    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        await stores.companies.create_company(
            CompanyContext(company_id=company_id, name="Uncertain HTTP Handoff")
        )
        policy = await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.DAILY,
                limit_usd=1.0,
            )
        )
        agent = await stores.agent_registry.create_agent_role(
            AgentRole(
                company_id=company_id,
                agent_id=agent_id,
                display_name="HTTP Uncertain Runner",
                adapter_type="http",
                permissions=["work.execute", "adapter:http", "tool:wakeup"],
                adapter_config={
                    "base_url": "http://agent.test",
                    "contract_version": "1.0",
                    "max_cost_usd": 0.3,
                },
            )
        )
        work = await stores.work_items.create_work_item(
            WorkItem(
                company_id=company_id,
                title="Work whose HTTP effect is uncertain",
                status=WorkItemStatus.READY,
                owner_agent_id=agent_id,
            )
        )
        work_item_id = work.work_item_id

        call_count = 0

        async def uncertain_then_succeed(_runner, _config, _request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise AgentWakeupError(
                    "executor_effects_uncertain",
                    status_code=409,
                    error_category="uncertain_effects",
                )
            return {
                "status": "ok",
                "adapter": "http",
                "cost_usd": 0.1,
                "summary": "Completed after operator recovery",
                "response": {"result": "reviewed retry"},
                "artifact_references": [],
            }

        monkeypatch.setattr(ControlPlaneAgentRunner, "_execute_http", uncertain_then_succeed)
        runner = ControlPlaneAgentRunner(stores.agent_operations)
        with pytest.raises(AgentWakeupError, match="executor_effects_uncertain") as failure:
            await runner.wake(
                agent,
                input_payload={"task": "perform external action"},
                actor_id="human:operator",
                work_item_id=work_item_id,
                idempotency_key="http-uncertain-first-attempt",
            )
        assert failure.value.error_category == "uncertain_effects"
        first_run = (
            await stores.agent_operations.list_agent_runs(
                company_id=CompanyId(company_id), agent_id=agent_id
            )
        )[0]
        lease = await session.scalar(
            select(ExecutionLeaseTable).where(ExecutionLeaseTable.run_id == first_run.run_id)
        )
        reservation = await session.scalar(
            select(ExecutionReservationTable).where(
                ExecutionReservationTable.execution_id == lease.execution_id
            )
        )
        assert first_run.status == "running"
        assert lease.state == "recovery_required"
        assert reservation.state == "reserved"
        assert float(reservation.amount_usd) == pytest.approx(0.3)
        assert (
            await stores.agent_operations.list_budget_usage(
                company_id=CompanyId(company_id), run_id=first_run.run_id
            )
            == []
        )
        await session.commit()

    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        recovered = await SqlAlchemyExecutionGovernanceStore(session).recover(
            run_id=first_run.run_id,
            company_id=company_id,
            reason="Receiver state checked; retry is safe after operator review.",
            actor_id="human:board",
        )
        await session.commit()
        assert recovered["state"] == "failed"
        reconciled = await stores.agent_runs.get_agent_run(AgentRunId(first_run.run_id))
        assert reconciled is not None
        assert reconciled.status == "failed"
        assert reconciled.error_category == "operator_reconciled_abandoned_execution"
        usage = await stores.agent_operations.list_budget_usage(
            company_id=CompanyId(company_id), run_id=first_run.run_id
        )
        assert len(usage) == 1
        assert usage[0].cost_usd == pytest.approx(0.3)
        assert usage[0].metadata["charged_ceiling"] is True

    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        retry_agent = await stores.agent_registry.get_agent_role(
            company_id=CompanyId(company_id), agent_id=AgentRoleId(agent_id)
        )
        assert retry_agent is not None
        retried = await ControlPlaneAgentRunner(stores.agent_operations).wake(
            retry_agent,
            input_payload={"task": "perform external action"},
            actor_id="human:operator",
            work_item_id=work_item_id,
            idempotency_key="http-uncertain-reviewed-retry",
        )
        assert retried.output["status"] == "ok"
        all_usage = await stores.agent_operations.list_budget_usage(
            company_id=CompanyId(company_id),
            limit=10,
        )
        assert sorted(row.cost_usd for row in all_usage) == [0.1, 0.3]
        reservations = (
            await session.scalars(
                select(ExecutionReservationTable).where(
                    ExecutionReservationTable.budget_id == policy.budget_id
                )
            )
        ).all()
        assert len(reservations) == 2
        assert {row.state for row in reservations} == {"settled"}


@pytest.mark.asyncio
async def test_budget_window_ignores_prior_period_usage_for_current_reservation(
    execution_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = "cmp_exec_period_window"
    agent_id = "period-window-runner"
    _enable_process(monkeypatch, agent_id)
    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        await stores.companies.create_company(
            CompanyContext(company_id=company_id, name="Period Window")
        )
        policy = await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.DAILY,
                limit_usd=0.5,
            )
        )
        # Record yesterday's spend; today's ceiling should still fit the daily limit.
        await stores.budgets.record_budget_usage(
            BudgetUsage(
                company_id=company_id,
                budget_id=policy.budget_id,
                cost_usd=5.0,
                model="prior-day",
                created_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        agent, _ = await _seed_agent(
            session,
            company_id=CompanyId(company_id),
            agent_id=agent_id,
            command=[sys.executable, "-c", "print('ok')"],
            ceiling=0.5,
        )
        result = await ControlPlaneAgentRunner(stores.agent_operations).wake(
            agent,
            input_payload={"task": "current period"},
        )
        assert result.output["status"] == "ok"
        usage = await stores.budgets.list_budget_usage(
            company_id=CompanyId(company_id),
            budget_id=BudgetPolicyId(policy.budget_id),
        )
        assert sorted(item.cost_usd for item in usage) == [0.5, 5.0]


@pytest.mark.asyncio
async def test_claim_checkpoint_survives_crash_and_expiry_requires_recovery(
    execution_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    company_id = "cmp_exec_recovery"
    agent_id = "recovery-runner"
    async with execution_session_factory() as session:
        agent, _ = await _seed_agent(
            session,
            company_id=company_id,
            agent_id=agent_id,
            command=[sys.executable, "-c", "print('unused')"],
        )
        governance = SqlAlchemyExecutionGovernanceStore(session)
        ticket = await governance.claim(
            agent,
            run_id="run_crash_before_dispatch",
            payload={"task": "durable claim"},
            work_item_id=None,
            goal_id=None,
            actor_id="human:operator",
            idempotency_key="crash-before-dispatch",
        )
        await start_agent_wakeup_run(
            ControlPlaneStores(session).agent_operations,
            agent,
            input_payload={"task": "durable claim"},
            actor_id="human:operator",
            trace_id="trace-crash-recovery",
            goal_id=None,
            work_item_id=None,
            trigger="manual_wakeup",
            run_id=ticket.run_id,
        )
        await governance.checkpoint()
        assert await governance.control_action(ticket) == "resume"
        pause = await governance.request_control(
            run_id=ticket.run_id,
            company_id=company_id,
            action="pause",
            reason="Operator is checking the external workspace.",
            actor_id="human:operator",
        )
        assert pause["state"] == "requested"
        assert await governance.control_action(ticket) == "pause"
        await governance.request_control(
            run_id=ticket.run_id,
            company_id=company_id,
            action="resume",
            reason="The workspace check is complete.",
            actor_id="human:operator",
        )
        assert await governance.control_action(ticket) == "resume"

    async with execution_session_factory() as session:
        lease = await session.get(ExecutionLeaseTable, ticket.execution_id)
        assert lease is not None
        assert lease.state == "running"
        assert lease.run_id == "run_crash_before_dispatch"
        running_run = await ControlPlaneStores(session).agent_runs.get_agent_run(
            AgentRunId(ticket.run_id)
        )
        assert running_run is not None
        assert running_run.status == "running"
        lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with execution_session_factory() as session:
        stores = ControlPlaneStores(session)
        reloaded_agent = await stores.agent_registry.get_agent_role(
            company_id=CompanyId(company_id),
            agent_id=AgentRoleId(agent_id),
        )
        assert reloaded_agent is not None
        with pytest.raises(ExecutionDenied, match="execution_recovery_required"):
            await SqlAlchemyExecutionGovernanceStore(session).claim(
                reloaded_agent,
                run_id="run_must_not_replay",
                payload={"task": "durable claim"},
                work_item_id=None,
                goal_id=None,
                actor_id="human:operator",
                idempotency_key="crash-before-dispatch",
            )
        lease = await session.get(ExecutionLeaseTable, ticket.execution_id)
        assert lease is not None
        assert lease.state == "recovery_required"
        assert lease.run_id == "run_crash_before_dispatch"
        recovered = await SqlAlchemyExecutionGovernanceStore(session).recover(
            run_id=ticket.run_id,
            company_id=company_id,
            reason="The process was checked and no external effect occurred.",
            actor_id="human:operator",
        )
        await session.commit()
        assert recovered == {
            "run_id": ticket.run_id,
            "state": "failed",
            "handoff": "operator_reviewed_retry",
        }
        reconciled_run = await stores.agent_runs.get_agent_run(AgentRunId(ticket.run_id))
        assert reconciled_run is not None
        assert reconciled_run.status == "failed"
        assert reconciled_run.error_category == "operator_reconciled_abandoned_execution"
        assert len(await stores.agent_runs.list_agent_runs(company_id=CompanyId(company_id))) == 1
        lease = await session.get(ExecutionLeaseTable, ticket.execution_id)
        assert lease is not None
        assert lease.state == "failed"


@pytest.mark.asyncio
async def test_postgres_claims_serialize_same_resource_in_generated_schema() -> None:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL concurrency tests")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must use PostgreSQL for row-lock coverage")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = f"test_execution_{uuid4().hex}"
    root_engine = create_async_engine(url)
    async with root_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = root_engine.execution_options(schema_translate_map={None: schema})
    try:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
        factory = async_sessionmaker(scoped_engine, expire_on_commit=False)
        company_id = f"cmp_{uuid4().hex[:20]}"
        agent_id = f"agent-{uuid4().hex[:20]}"
        async with factory() as session:
            agent, work = await _seed_agent(
                session,
                company_id=company_id,
                agent_id=agent_id,
                command=[sys.executable, "-c", "print('unused')"],
            )
            work_item = await ControlPlaneStores(session).work_items.create_work_item(
                WorkItem(
                    company_id=company_id,
                    title="Shared resource",
                    status=WorkItemStatus.READY,
                    owner_agent_id=agent_id,
                )
            )
            await session.commit()

        async def claim_once(key: str, run_id: str) -> ExecutionTicket | ExecutionDenied:
            async with factory() as session:
                try:
                    ticket = await SqlAlchemyExecutionGovernanceStore(session).claim(
                        agent,
                        run_id=run_id,
                        payload={"task": "serialize"},
                        work_item_id=work_item.work_item_id,
                        goal_id=None,
                        actor_id="human:operator",
                        idempotency_key=key,
                    )
                    await session.commit()
                    return ticket
                except ExecutionDenied as exc:
                    await session.rollback()
                    return exc

        outcomes = await asyncio.gather(
            claim_once("concurrent-one", "run_concurrent_one"),
            claim_once("concurrent-two", "run_concurrent_two"),
        )
        successful = [value for value in outcomes if not isinstance(value, ExecutionDenied)]
        denied = [value for value in outcomes if isinstance(value, ExecutionDenied)]
        assert len(successful) == 1
        assert len(denied) == 1
        assert denied[0].reason == "execution_in_progress"
    finally:
        async with scoped_engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.drop_all)
        async with root_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


@pytest.mark.asyncio
async def test_postgres_company_budget_serializes_distinct_work_item_claims() -> None:
    async with _postgres_schema_factory("test_budget_claim") as factory:
        company_id = f"cmp_{uuid4().hex[:20]}"
        async with factory() as session:
            stores = ControlPlaneStores(session)
            await stores.companies.create_company(
                CompanyContext(company_id=company_id, name="Concurrent Budget")
            )
            policy = await stores.budgets.create_budget_policy(
                BudgetPolicy(
                    company_id=company_id,
                    scope=BudgetScope.COMPANY,
                    period=BudgetPeriod.DAILY,
                    limit_usd=1.0,
                )
            )
            agents_and_work = []
            for index in range(2):
                agent_id = f"budget-agent-{index}-{uuid4().hex[:8]}"
                agent = await stores.agent_registry.create_agent_role(
                    AgentRole(
                        company_id=company_id,
                        agent_id=agent_id,
                        display_name=f"Budget Agent {index}",
                        adapter_type="process",
                        permissions=["work.execute", "adapter:process", "tool:wakeup"],
                        adapter_config={
                            "command": [sys.executable, "-c", "print('unused')"],
                            "max_cost_usd": 0.75,
                        },
                    )
                )
                work = await stores.work_items.create_work_item(
                    WorkItem(
                        company_id=company_id,
                        title=f"Independent budget item {index}",
                        status=WorkItemStatus.READY,
                        owner_agent_id=agent_id,
                    )
                )
                agents_and_work.append((agent, work))
            await session.commit()

        async def claim_once(agent: AgentRole, work: WorkItem, index: int):
            async with factory() as session:
                try:
                    ticket = await SqlAlchemyExecutionGovernanceStore(session).claim(
                        agent,
                        run_id=f"run_budget_claim_{index}_{uuid4().hex[:8]}",
                        payload={"task": "reserve company budget"},
                        work_item_id=work.work_item_id,
                        goal_id=None,
                        actor_id="human:operator",
                        idempotency_key=f"budget-reservation-{index}",
                    )
                    await session.commit()
                    return ticket
                except ExecutionDenied as exc:
                    await session.rollback()
                    return exc

        results = await asyncio.gather(
            *(claim_once(agent, work, index) for index, (agent, work) in enumerate(agents_and_work))
        )
        tickets = [value for value in results if not isinstance(value, ExecutionDenied)]
        denials = [value for value in results if isinstance(value, ExecutionDenied)]
        assert len(tickets) == 1
        assert len(denials) == 1
        assert denials[0].reason == "execution_budget_exceeded"

        async with factory() as session:
            reservations = (
                await session.scalars(
                    select(ExecutionReservationTable).where(
                        ExecutionReservationTable.budget_id == policy.budget_id,
                        ExecutionReservationTable.state == "reserved",
                    )
                )
            ).all()
        assert len(reservations) == 1
        assert sum(float(row.amount_usd) for row in reservations) == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_postgres_heartbeat_claim_rechecks_recent_completion_under_company_lock() -> None:
    async with _postgres_schema_factory("test_heartbeat_boundary") as factory:
        company_id = f"cmp_{uuid4().hex[:20]}"
        agent_id = f"heartbeat-{uuid4().hex[:16]}"
        async with factory() as session:
            stores = ControlPlaneStores(session)
            await stores.companies.create_company(
                CompanyContext(company_id=company_id, name="Heartbeat Boundary")
            )
            agent = await stores.agent_registry.create_agent_role(
                AgentRole(
                    company_id=company_id,
                    agent_id=agent_id,
                    display_name="Heartbeat Boundary Agent",
                    adapter_type="builtin",
                    adapter_config={
                        "heartbeat_enabled": True,
                        "heartbeat_interval_seconds": 60,
                    },
                )
            )
            first = await ControlPlaneAgentRunner(stores.agent_operations).wake(
                agent,
                input_payload={"trigger": "heartbeat", "heartbeat_interval_seconds": 60},
                actor_id="control-plane:scheduler",
                trigger="scheduled_heartbeat",
                idempotency_key="heartbeat-slot-before-boundary",
            )
            assert first.run_id
            await session.commit()

        async with factory() as session:
            stores = ControlPlaneStores(session)
            recent = await stores.agent_runs.get_agent_run(AgentRunId(first.run_id))
            reloaded_agent = await stores.agent_registry.get_agent_role(
                company_id=CompanyId(company_id), agent_id=AgentRoleId(agent_id)
            )
            assert recent is not None
            assert recent.status == "succeeded"
            assert reloaded_agent is not None
            with pytest.raises(ExecutionDenied, match="heartbeat_interval_not_elapsed"):
                await SqlAlchemyExecutionGovernanceStore(session).claim(
                    reloaded_agent,
                    run_id=f"run_heartbeat_adjacent_{uuid4().hex[:8]}",
                    payload={"trigger": "heartbeat", "heartbeat_interval_seconds": 60},
                    work_item_id=None,
                    goal_id=None,
                    actor_id="control-plane:scheduler",
                    idempotency_key="heartbeat-adjacent-fresh-key",
                )


@pytest.mark.parametrize("ceiling", [0.0, 0.3])
@pytest.mark.asyncio
async def test_explicit_metered_cost_equal_to_ceiling_is_not_an_estimated_charge(
    execution_session_factory, monkeypatch, ceiling
):
    monkeypatch.setattr("shared.config.settings.control_plane_local_adapter_enabled", True)
    monkeypatch.setattr(
        "shared.config.settings.control_plane_local_adapter_allowlist", "process:metered-cost"
    )
    async with execution_session_factory() as session:
        agent, _ = await _seed_agent(
            session,
            company_id="cmp_metered",
            agent_id="metered-cost",
            command=[sys.executable, "-c", "pass"],
            ceiling=ceiling,
        )
        stores = ControlPlaneStores(session)
        await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=agent.company_id,
                scope=BudgetScope.COMPANY,
                period=BudgetPeriod.DAILY,
                limit_usd=10,
            )
        )
        agent.adapter_config["contract_version"] = "1.0"
        agent.adapter_config["command"] = [
            sys.executable,
            "-c",
            'import json; print(json.dumps({"schema_version":"1.0","status":"succeeded","summary":"metered output","output":{"report":"ready"},"cost_usd":'
            + str(ceiling)
            + "}))",
        ]
        from shared.control_plane.tables import AgentRoleTable

        persisted = await session.scalar(
            select(AgentRoleTable).where(
                AgentRoleTable.company_id == agent.company_id,
                AgentRoleTable.agent_id == agent.agent_id,
            )
        )
        assert persisted is not None
        persisted.adapter_config = agent.adapter_config
        await session.flush()
        await ControlPlaneAgentRunner(stores.agent_operations).wake(
            agent, idempotency_key="metered-zero", actor_id="operator"
        )
        charges = await stores.budgets.list_budget_usage(company_id=CompanyId(agent.company_id))
        assert len(charges) == 1
        assert charges[0].cost_usd == ceiling
        assert charges[0].metadata["charged_ceiling"] is False
