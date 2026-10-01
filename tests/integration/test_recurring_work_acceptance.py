"""PostgreSQL acceptance for recurring Control Plane heartbeat work.

This exercises the current recurring-work surface: explicitly opted-in agent
heartbeats. It uses a generated schema and a local process executor so the
database claim and business effect are both observable without touching shared
or pilot data.
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
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.control_plane.agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from shared.control_plane.domain.executor_contract import executor_capabilities
from shared.control_plane.models import (
    AgentRole,
    ApprovalStatus,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    WorkItem,
    WorkItemStatus,
)
from shared.control_plane.scheduler import ControlPlaneHeartbeatScheduler
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import AgentRunTable, control_plane_metadata
from shared.core.identifiers import CompanyId


@asynccontextmanager
async def _postgres_schema_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not configured for recurring-work acceptance")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL must use PostgreSQL for recurring-work acceptance")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")

    schema = f"test_recurring_work_{uuid4().hex}"
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


def _enable_process(monkeypatch: pytest.MonkeyPatch, agent_id: str) -> None:
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_enabled", True
    )
    monkeypatch.setattr(
        "shared.control_plane.agent_runner.settings.control_plane_local_adapter_allowlist",
        f"process:{agent_id}",
    )


def _business_effect_command(output_path: Path) -> list[str]:
    source = (
        "import json,sys; request=json.load(sys.stdin); "
        f"open({str(output_path)!r}, 'a', encoding='utf-8').write("
        "request['input']['scheduled_at'] + '\\n'); "
        "print(json.dumps({'schema_version':'1.0','status':'succeeded',"
        "'summary':'recurring business effect recorded','cost_usd':0.02}))"
    )
    return [sys.executable, "-c", source]


@pytest.mark.asyncio
async def test_recurring_heartbeat_claims_each_due_slot_once_across_contenders_and_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two scheduler contenders cannot duplicate a due slot or its side effect."""
    async with _postgres_schema_factory() as factory:
        company_id = f"cmp_{uuid4().hex[:20]}"
        agent_id = f"recurring-{uuid4().hex[:16]}"
        effect_file = tmp_path / "business-effects.txt"
        _enable_process(monkeypatch, agent_id)

        async with factory() as session:
            stores = ControlPlaneStores(session)
            await stores.companies.create_company(
                CompanyContext(company_id=company_id, name="Recurring Work Acceptance")
            )
            await stores.budgets.create_budget_policy(
                BudgetPolicy(
                    company_id=company_id,
                    scope=BudgetScope.COMPANY,
                    period=BudgetPeriod.DAILY,
                    limit_usd=5.0,
                )
            )
            agent = await stores.agent_registry.create_agent_role(
                AgentRole(
                    company_id=company_id,
                    agent_id=agent_id,
                    display_name="Recurring Work Executor",
                    adapter_type="process",
                    permissions=["work.execute", "adapter:process", "tool:wakeup"],
                    adapter_config={
                        "command": _business_effect_command(effect_file),
                        "timeout_sec": 10,
                        "max_cost_usd": 0.10,
                        "contract_version": "1.0",
                        "heartbeat_enabled": True,
                        "heartbeat_interval_seconds": 60,
                    },
                )
            )
            # The existing heartbeat scheduler is role-scoped and has no
            # work-item selector. Keep a durable item in the same context and
            # assert the actual run linkage contract below (agent/run/audit).
            work_item = await stores.work_items.create_work_item(
                WorkItem(
                    company_id=company_id,
                    title="Recurring synthetic business task",
                    status=WorkItemStatus.READY,
                    owner_agent_id=agent_id,
                )
            )
            await session.commit()

        base_time = datetime.now(UTC)

        async def tick(now: datetime) -> list:
            async with factory() as session:
                outcomes = await ControlPlaneHeartbeatScheduler(
                    ControlPlaneStores(session).agent_operations
                ).run_due_once(company_id=company_id, now=now)
                await session.commit()
                return outcomes

        # Independent sessions model two contenders seeing the same due role.
        first_slot = await asyncio.gather(tick(base_time), tick(base_time))
        first_runs = [result.run_id for batch in first_slot for result in batch if result.run_id]
        assert len(set(first_runs)) == 1
        assert sum(result.status == "succeeded" for batch in first_slot for result in batch) >= 1
        assert all(
            result.status in {"succeeded", "skipped"}
            or (result.status == "failed" and result.error == "execution_in_progress")
            for batch in first_slot
            for result in batch
        ), first_slot

            # Simulate a second due slot by advancing persisted completion time
            # instead of sleeping a full interval. The governance claim checks
            # wall-clock time independently of the scheduler's injected due time.
        async with factory() as session:
            run_row = await session.scalar(
                select(AgentRunTable).where(AgentRunTable.run_id == first_runs[0])
            )
            assert run_row is not None
            run_row.completed_at = base_time - timedelta(seconds=120)
            await session.commit()

        # Once the first run has completed, a later heartbeat window is a
        # distinct execution loaded through a fresh store/session.
        second_slot = await tick(base_time + timedelta(seconds=120))
        assert len(second_slot) == 1
        assert second_slot[0].status == "succeeded", second_slot[0]
        assert second_slot[0].run_id not in first_runs

        effect_slots = effect_file.read_text(encoding="utf-8").splitlines()
        assert len(effect_slots) == 2
        assert len(set(effect_slots)) == 2

        async with factory() as session:
            stores = ControlPlaneStores(session)
            runs = await stores.agent_runs.list_agent_runs(
                company_id=CompanyId(company_id), agent_id=agent_id, limit=10
            )
            assert len(runs) == 2
            assert {run.run_id for run in runs} == {first_runs[0], second_slot[0].run_id}
            assert all(run.status == "succeeded" for run in runs)
            assert all(run.input_event["payload"]["input"]["trigger"] == "heartbeat" for run in runs)
            assert all(run.work_item_id is None for run in runs)
            assert all(run.cost_usd == pytest.approx(0.02) for run in runs)
            assert all(run.metadata["cost_is_estimate"] is False for run in runs)
            usage = await stores.budgets.list_budget_usage(company_id=CompanyId(company_id), limit=10)
            assert len(usage) == 2
            assert {item.run_id for item in usage} == {run.run_id for run in runs}
            assert sum(run.cost_usd for run in runs) == pytest.approx(
                sum(item.cost_usd for item in usage)
            )
            assert sum(item.cost_usd for item in usage) == pytest.approx(0.04)

            audits = await stores.audit_events.list_audit_events(company_id=company_id, limit=50)
            run_audits = [event for event in audits if event.run_id in {run.run_id for run in runs}]
            assert run_audits
            assert {event.run_id for event in run_audits} == {run.run_id for run in runs}

        assert agent.agent_id == agent_id
        assert work_item.owner_agent_id == agent_id
        capabilities = executor_capabilities("process")
        assert capabilities["automatic_crash_resume"] is False


@pytest.mark.asyncio
async def test_recurring_work_governance_denials_leave_business_effect_untouched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pending approval and exhausted budget stop local dispatch before effects."""
    async with _postgres_schema_factory() as factory:
        company_id = f"cmp_{uuid4().hex[:20]}"
        approval_agent_id = f"approval-{uuid4().hex[:12]}"
        budget_agent_id = f"budget-{uuid4().hex[:12]}"
        effect_file = tmp_path / "denied-effects.txt"
        _enable_process(monkeypatch, approval_agent_id)
        _enable_process(monkeypatch, budget_agent_id)

        async with factory() as session:
            stores = ControlPlaneStores(session)
            await stores.companies.create_company(
                CompanyContext(company_id=company_id, name="Recurring Denial Acceptance")
            )
            await stores.budgets.create_budget_policy(
                BudgetPolicy(
                    company_id=company_id,
                    scope=BudgetScope.COMPANY,
                    period=BudgetPeriod.DAILY,
                    limit_usd=0.05,
                )
            )
            command = _business_effect_command(effect_file)
            approval_agent = await stores.agent_registry.create_agent_role(
                AgentRole(
                    company_id=company_id,
                    agent_id=approval_agent_id,
                    display_name="Approval Gated Executor",
                    adapter_type="process",
                    permissions=["work.execute", "adapter:process", "tool:wakeup"],
                    adapter_config={"command": command, "max_cost_usd": 0.10},
                )
            )
            budget_agent = await stores.agent_registry.create_agent_role(
                AgentRole(
                    company_id=company_id,
                    agent_id=budget_agent_id,
                    display_name="Budget Gated Executor",
                    adapter_type="process",
                    permissions=["work.execute", "adapter:process", "tool:wakeup"],
                    adapter_config={
                        "command": command,
                        "max_cost_usd": 0.10,
                        "heartbeat_enabled": True,
                        "heartbeat_interval_seconds": 60,
                    },
                )
            )
            approval_work = await stores.work_items.create_work_item(
                WorkItem(
                    company_id=company_id,
                    title="Approval gated recurring work",
                    status=WorkItemStatus.READY,
                    owner_agent_id=approval_agent_id,
                    approval_required=True,
                )
            )
            await session.commit()

        async with factory() as session:
            with pytest.raises(AgentWakeupError, match="execution_approval_required"):
                await ControlPlaneAgentRunner(ControlPlaneStores(session).agent_operations).wake(
                    approval_agent,
                    input_payload={"task": "publish recurring report"},
                    actor_id="control-plane:scheduler",
                    work_item_id=approval_work.work_item_id,
                    trigger="scheduled_heartbeat",
                    idempotency_key="approval-required-recurring-slot",
                )
            approvals = await ControlPlaneStores(session).approvals.list_approvals(
                company_id=CompanyId(company_id)
            )
            assert len(approvals) == 1
            assert approvals[0].status == ApprovalStatus.PENDING.value

        async with factory() as session:
            results = await ControlPlaneHeartbeatScheduler(
                ControlPlaneStores(session).agent_operations
            ).run_due_once(company_id=company_id, now=datetime(2026, 1, 1, tzinfo=UTC))
            budget_result = next(result for result in results if result.agent_id == budget_agent_id)
            assert budget_result.status == "failed"
            assert budget_result.error == "execution_budget_exceeded"
            await session.commit()

        assert not effect_file.exists()
        assert approval_agent.agent_id == approval_agent_id
        assert budget_agent.agent_id == budget_agent_id
