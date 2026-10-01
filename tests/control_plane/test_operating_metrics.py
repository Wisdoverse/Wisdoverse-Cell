from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api_routes.operating_metrics import (
    OperatingMetricsReader,
    create_operating_metrics_router,
)
from shared.control_plane.execution_models import ExecutionLeaseTable, ExecutionReservationTable
from shared.control_plane.operating_metrics_store import SqlAlchemyOperatingMetricsStore
from shared.control_plane.operator_auth import OperatorPrincipal, require_operator
from shared.control_plane.outcome_models import OutcomeAcceptanceTable
from shared.control_plane.tables import (
    AgentRunTable,
    ApprovalRequestTable,
    ArtifactTable,
    BudgetPolicyTable,
    BudgetUsageTable,
    CompanyContextTable,
    ControlPlaneEventOutboxTable,
    WorkItemTable,
)

COMPANY = "cmp_metrics_test"
OTHER_COMPANY = "cmp_metrics_other"


def _run(
    company_id: str,
    run_id: str,
    started_at: datetime,
    *,
    cost: float,
    status: str = "succeeded",
    work_item_id: str | None = None,
    error_category: str | None = None,
) -> AgentRunTable:
    return AgentRunTable(
        run_id=run_id,
        company_id=company_id,
        agent_id="agent-test",
        status=status,
        work_item_id=work_item_id,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=5),
        error_category=error_category,
        cost_usd=cost,
        metadata_json={},
        output_events=[],
    )


async def _add_company(session: AsyncSession, company_id: str) -> None:
    session.add(CompanyContextTable(company_id=company_id, name=company_id))
    await session.flush()


def _acceptance(
    acceptance_id: str,
    company_id: str,
    work_item_id: str,
    artifact_id: str,
    run_id: str,
    verdict: str,
    now: datetime,
) -> OutcomeAcceptanceTable:
    return OutcomeAcceptanceTable(
        acceptance_id=acceptance_id,
        company_id=company_id,
        work_item_id=work_item_id,
        artifact_id=artifact_id,
        run_id=run_id,
        artifact_hash="hash",
        verdict=verdict,
        actor_id="operator",
        reason="Reviewed",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_full_cost_includes_failed_attempts_and_deduplicates_policy_charges(
    db_session: AsyncSession,
) -> None:
    now = datetime(2025, 1, 1, 12, tzinfo=UTC)
    await _add_company(db_session, COMPANY)
    await _add_company(db_session, OTHER_COMPANY)
    successful = _run(
        COMPANY,
        "run-success",
        now - timedelta(minutes=9),
        cost=1,
        work_item_id="work-success",
    )
    failed = _run(
        COMPANY,
        "run-failed",
        now - timedelta(minutes=2),
        cost=2,
        status="failed",
        error_category="adapter_disabled",
    )
    foreign = _run(OTHER_COMPANY, "run-foreign", now - timedelta(minutes=3), cost=100)
    db_session.add_all([successful, failed, foreign])
    db_session.add_all(
        [
            WorkItemTable(
                work_item_id="work-success",
                company_id=COMPANY,
                title="Success",
                created_at=now - timedelta(minutes=9, seconds=30),
                metadata_json={"acceptance_id": "accept-success"},
            ),
            ArtifactTable(
                artifact_id="artifact-success",
                company_id=COMPANY,
                artifact_type="report",
                title="Result",
                uri="local:test",
                run_id="run-success",
                work_item_id="work-success",
            ),
            _acceptance(
                "accept-success",
                COMPANY,
                "work-success",
                "artifact-success",
                "run-success",
                "accepted",
                now,
            ),
            # Older accepted history must not count once the current work-item pointer
            # has moved to a later rejection.
            WorkItemTable(
                work_item_id="work-rejected",
                company_id=COMPANY,
                title="Rejected",
                metadata_json={"acceptance_id": "accept-latest-rejection"},
            ),
            ArtifactTable(
                artifact_id="artifact-rejected",
                company_id=COMPANY,
                artifact_type="report",
                title="Rejected",
                uri="local:rejected",
                run_id="run-success",
                work_item_id="work-rejected",
            ),
            _acceptance(
                "accept-history",
                COMPANY,
                "work-rejected",
                "artifact-rejected",
                "run-success",
                "accepted",
                now - timedelta(days=1),
            ),
            _acceptance(
                "accept-latest-rejection",
                COMPANY,
                "work-rejected",
                "artifact-rejected",
                "run-success",
                "rejected",
                now,
            ),
        ]
    )
    db_session.add_all(
        [
            BudgetPolicyTable(
                budget_id="budget-one",
                company_id=COMPANY,
                scope="company",
                period="daily",
                limit_usd=100,
            ),
            BudgetPolicyTable(
                budget_id="budget-two",
                company_id=COMPANY,
                scope="agent",
                scope_id="agent-test",
                period="daily",
                limit_usd=100,
            ),
        ]
    )
    db_session.add_all(
        [
            ExecutionLeaseTable(
                execution_id="exec-success",
                company_id=COMPANY,
                resource_id="work:work-success",
                intent_hash="intent",
                run_id="run-success",
                owner_id="owner",
                state="succeeded",
                control_action="resume",
                expires_at=now,
                created_at=now - timedelta(minutes=9),
            ),
            ExecutionLeaseTable(
                execution_id="exec-failed",
                company_id=COMPANY,
                resource_id="work:failed",
                intent_hash="intent-failed",
                run_id="run-failed",
                owner_id="owner",
                state="failed",
                control_action="resume",
                expires_at=now,
                created_at=now - timedelta(minutes=2),
            ),
            ExecutionReservationTable(
                execution_id="exec-success",
                budget_id="budget-one",
                amount_usd=10,
                state="settled",
                created_at=now,
            ),
            ExecutionReservationTable(
                execution_id="exec-success",
                budget_id="budget-two",
                amount_usd=10,
                state="settled",
                created_at=now,
            ),
            ExecutionReservationTable(
                execution_id="exec-failed",
                budget_id="budget-one",
                amount_usd=4,
                state="settled",
                created_at=now,
            ),
            ExecutionReservationTable(
                execution_id="exec-failed",
                budget_id="budget-two",
                amount_usd=4,
                state="settled",
                created_at=now,
            ),
            # One charge recorded against overlapping budget policies is counted once.
            BudgetUsageTable(
                usage_id="usage-success-one",
                company_id=COMPANY,
                budget_id="budget-one",
                cost_usd=1,
                model="m",
                run_id="run-success",
                metadata_json={"execution_id": "exec-success"},
                created_at=now,
            ),
            BudgetUsageTable(
                usage_id="usage-success-two",
                company_id=COMPANY,
                budget_id="budget-two",
                cost_usd=1,
                model="m",
                run_id="run-success",
                metadata_json={"execution_id": "exec-success"},
                created_at=now,
            ),
            BudgetUsageTable(
                usage_id="usage-failed-one",
                company_id=COMPANY,
                budget_id="budget-one",
                cost_usd=2,
                model="m",
                run_id="run-failed",
                metadata_json={"execution_id": "exec-failed", "charged_ceiling": True},
                created_at=now,
            ),
            BudgetUsageTable(
                usage_id="usage-failed-two",
                company_id=COMPANY,
                budget_id="budget-two",
                cost_usd=2,
                model="m",
                run_id="run-failed",
                metadata_json={"execution_id": "exec-failed"},
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    metrics = await SqlAlchemyOperatingMetricsStore(db_session).get_metrics(COMPANY, now=now)
    assert metrics["runs"]["total"] == 2
    assert metrics["runs"]["by_status"] == {"failed": 1, "succeeded": 1}
    assert metrics["runs"]["adapter_errors"] == 1
    assert metrics["runs"]["success_rate"] == 0.5
    assert metrics["queue_delay"]["p95_seconds"] == 30
    assert metrics["queue_delay"]["sample_size"] == 1
    assert metrics["queue_delay"]["source"].startswith("work_item.created_at")
    assert metrics["costs"]["accepted_outcome_count"] == 1
    assert metrics["costs"]["estimated_ceiling_usd_per_accepted_outcome"] == 14
    assert metrics["costs"]["deduplicated_budget_usage_usd_total"] == 3
    assert metrics["costs"]["failed_run_reported_cost_usd"] == 2
    assert metrics["costs"]["failed_run_budget_charges_usd"] == 2
    assert metrics["costs"]["charged_ceiling_usd_total"] == 2
    assert metrics["costs"]["charged_ceiling_charge_count"] == 1
    assert metrics["costs"]["full_cost_usd_per_accepted_outcome"] == 3


@pytest.mark.asyncio
async def test_distinct_usage_rows_with_same_trace_are_both_counted(
    db_session: AsyncSession,
) -> None:
    now = datetime(2025, 1, 1, 12, tzinfo=UTC)
    await _add_company(db_session, COMPANY)
    db_session.add_all(
        [
            _run(COMPANY, "run-a", now - timedelta(minutes=1), cost=0),
            WorkItemTable(
                work_item_id="work-a",
                company_id=COMPANY,
                title="Accepted",
                metadata_json={"acceptance_id": "accept-a"},
            ),
            ArtifactTable(
                artifact_id="artifact-a",
                company_id=COMPANY,
                artifact_type="report",
                title="Accepted",
                uri="local:a",
                run_id="run-a",
                work_item_id="work-a",
            ),
            _acceptance("accept-a", COMPANY, "work-a", "artifact-a", "run-a", "accepted", now),
            BudgetPolicyTable(
                budget_id="budget-a",
                company_id=COMPANY,
                scope="company",
                period="daily",
                limit_usd=100,
            ),
            BudgetUsageTable(
                usage_id="usage-a",
                company_id=COMPANY,
                budget_id="budget-a",
                cost_usd=0.5,
                model="m",
                run_id="run-a",
                trace_id="shared-trace",
                metadata_json={},
                created_at=now,
            ),
            BudgetUsageTable(
                usage_id="usage-b",
                company_id=COMPANY,
                budget_id="budget-a",
                cost_usd=0.75,
                model="m",
                run_id="run-a",
                trace_id="shared-trace",
                metadata_json={},
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    metrics = await SqlAlchemyOperatingMetricsStore(db_session).get_metrics(COMPANY, now=now)
    assert metrics["costs"]["deduplicated_budget_usage_usd_total"] == 1.25
    assert metrics["costs"]["full_cost_usd_per_accepted_outcome"] == 1.25
    assert metrics["costs"]["unmetered_run_count"] == 0


@pytest.mark.asyncio
async def test_metrics_include_old_approval_and_unresolved_delivery_ages(
    db_session: AsyncSession,
) -> None:
    now = datetime(2025, 1, 1, 12, tzinfo=UTC)
    await _add_company(db_session, COMPANY)
    db_session.add_all(
        [
            ApprovalRequestTable(
                approval_id="approval-old",
                company_id=COMPANY,
                category="technical",
                status="pending",
                requested_by="operator",
                source_agent_id="agent-test",
                proposed_action="review",
                reason="risk",
                risk="risk",
                rollback_note="rollback",
                created_at=now - timedelta(hours=2),
            ),
            ExecutionLeaseTable(
                execution_id="exec-old",
                company_id=COMPANY,
                resource_id="work:old",
                intent_hash="intent",
                run_id="run-old",
                owner_id="owner",
                state="recovery_required",
                control_action="resume",
                expires_at=now - timedelta(minutes=30),
                created_at=now - timedelta(hours=1),
            ),
            ControlPlaneEventOutboxTable(
                event_id="event-old",
                event_type="work.updated",
                source_agent="control-plane",
                payload={"company_id": COMPANY},
                status="pending",
                attempts=1,
                created_at=now - timedelta(minutes=20),
            ),
        ]
    )
    await db_session.flush()

    metrics = await SqlAlchemyOperatingMetricsStore(db_session).get_metrics(COMPANY, now=now)
    assert metrics["approvals"]["pending"] == 1
    assert metrics["approvals"]["oldest_pending_age_seconds"] == 7200
    assert metrics["unresolved_execution_leases"]["count"] == 1
    assert metrics["unresolved_execution_leases"]["oldest_age_seconds"] == 3600
    assert metrics["pending_outbox"]["count"] == 1
    assert metrics["pending_outbox"]["oldest_age_seconds"] == 1200
    assert metrics["export_policy"]["retention_days"] == 90


def test_metrics_routes_enforce_scope_and_emit_low_cardinality_prometheus() -> None:
    async def get_store() -> AsyncGenerator[OperatingMetricsReader, None]:
        yield _FakeMetricsStore()

    router = create_operating_metrics_router(get_store=get_store)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_operator] = lambda: OperatorPrincipal(
        "actor", frozenset({COMPANY}), frozenset({"control-plane:read"})
    )
    app.dependency_overrides[get_store] = lambda: _FakeMetricsStore()

    client = TestClient(app)
    denied = client.get(f"/operating-metrics/prometheus?company_id={OTHER_COMPANY}")
    allowed = client.get(f"/operating-metrics/prometheus?company_id={COMPANY}")
    json_metrics = client.get(f"/operating-metrics?company_id={COMPANY}")
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert json_metrics.status_code == 200
    assert json_metrics.json() == {
        "company_id": COMPANY,
        "approvals": {"oldest_pending_age_seconds": 42},
        "unresolved_execution_leases": {"count": 1},
        "pending_outbox": {"oldest_age_seconds": 60},
        "runs": {"adapter_errors": 2, "success_rate": 0.75},
        "queue_delay": {"p95_seconds": 12},
        "costs": {"full_cost_usd_per_accepted_outcome": 4.5},
    }
    body = allowed.text
    assert "control_plane_work_queue_delay_p95_seconds 12" in body
    assert "control_plane_run_success_rate 0.75" in body
    assert "control_plane_full_cost_usd_per_accepted_outcome 4.5" in body
    for metric_name in (
        "control_plane_pending_approval_oldest_age_seconds",
        "control_plane_unresolved_execution_leases",
        "control_plane_pending_outbox_oldest_age_seconds",
        "control_plane_adapter_errors_total",
        "control_plane_work_queue_delay_p95_seconds",
        "control_plane_run_success_rate",
        "control_plane_full_cost_usd_per_accepted_outcome",
    ):
        assert metric_name in body
    assert COMPANY not in body and OTHER_COMPANY not in body and "run-" not in body


class _FakeMetricsStore:
    async def get_metrics(self, company_id: str) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "approvals": {"oldest_pending_age_seconds": 42},
            "unresolved_execution_leases": {"count": 1},
            "pending_outbox": {"oldest_age_seconds": 60},
            "runs": {"adapter_errors": 2, "success_rate": 0.75},
            "queue_delay": {"p95_seconds": 12},
            "costs": {"full_cost_usd_per_accepted_outcome": 4.5},
        }


@pytest.mark.asyncio
async def test_full_cost_sums_disjoint_run_and_usage_ledger_costs(
    db_session: AsyncSession,
) -> None:
    now = datetime(2025, 1, 1, 12, tzinfo=UTC)
    await _add_company(db_session, COMPANY)
    db_session.add_all(
        [
            _run(COMPANY, "run-a", now - timedelta(minutes=2), cost=2),
            _run(COMPANY, "run-b", now - timedelta(minutes=1), cost=0),
            WorkItemTable(
                work_item_id="work-b",
                company_id=COMPANY,
                title="Accepted",
                metadata_json={"acceptance_id": "accept-b"},
            ),
            ArtifactTable(
                artifact_id="artifact-b",
                company_id=COMPANY,
                artifact_type="report",
                title="Accepted",
                uri="local:b",
                run_id="run-b",
                work_item_id="work-b",
            ),
            _acceptance("accept-b", COMPANY, "work-b", "artifact-b", "run-b", "accepted", now),
            BudgetPolicyTable(
                budget_id="budget-b",
                company_id=COMPANY,
                scope="company",
                period="daily",
                limit_usd=100,
            ),
            BudgetUsageTable(
                usage_id="usage-b",
                company_id=COMPANY,
                budget_id="budget-b",
                cost_usd=1,
                model="m",
                run_id="run-b",
                metadata_json={},
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    metrics = await SqlAlchemyOperatingMetricsStore(db_session).get_metrics(COMPANY, now=now)
    assert metrics["costs"]["full_cost_usd_total"] == 3
    assert metrics["costs"]["full_cost_usd_per_accepted_outcome"] == 3
