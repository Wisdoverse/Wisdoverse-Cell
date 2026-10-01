"""Company-scoped, read-only operational metrics queries."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .execution_models import ExecutionLeaseTable, ExecutionReservationTable
from .outcome_models import OutcomeAcceptanceTable
from .tables import (
    AgentRunTable,
    ApprovalRequestTable,
    BudgetUsageTable,
    ControlPlaneEventOutboxTable,
    WorkItemTable,
)

METRICS_EXPORT_RETENTION_DAYS = 90
WORK_ITEM_QUEUE_SAMPLE_LIMIT = 1000
TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled", "timed_out")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _age_seconds(now: datetime, timestamp: datetime | None) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, (now - _utc(timestamp)).total_seconds())


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    values.sort()
    return values[max(0, math.ceil(0.95 * len(values)) - 1)]


class SqlAlchemyOperatingMetricsStore:
    """Read aggregate health and outcome measures for one company."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_metrics(self, company_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        captured_at = _utc(now or datetime.now(UTC))

        # Counts are exact for company history. Only queue sample rows are bounded.
        status_result = await self._session.execute(
            select(AgentRunTable.status, func.count())
            .where(AgentRunTable.company_id == company_id)
            .group_by(AgentRunTable.status)
        )
        run_counts = {str(status): int(count) for status, count in status_result.all()}
        run_count = sum(run_counts.values())
        terminal_count = sum(run_counts.get(status, 0) for status in TERMINAL_RUN_STATUSES)
        success_count = run_counts.get("succeeded", 0)
        adapter_errors = await self._session.scalar(
            select(func.count())
            .select_from(AgentRunTable)
            .where(
                AgentRunTable.company_id == company_id,
                AgentRunTable.error_category.like("adapter%"),
            )
        )

        # Queue delay is work creation to first recorded run start, not lease
        # creation to run start (which measures dispatch latency instead).
        latest_work_items = (
            select(
                WorkItemTable.work_item_id.label("work_item_id"),
                WorkItemTable.created_at.label("created_at"),
            )
            .where(WorkItemTable.company_id == company_id)
            .order_by(WorkItemTable.created_at.desc(), WorkItemTable.work_item_id.desc())
            .limit(WORK_ITEM_QUEUE_SAMPLE_LIMIT)
            .subquery()
        )
        first_runs = (
            select(
                AgentRunTable.work_item_id.label("work_item_id"),
                func.min(AgentRunTable.started_at).label("first_started_at"),
            )
            .join(
                latest_work_items,
                latest_work_items.c.work_item_id == AgentRunTable.work_item_id,
            )
            .where(AgentRunTable.company_id == company_id)
            .group_by(AgentRunTable.work_item_id)
            .subquery()
        )
        queue_rows = await self._session.execute(
            select(latest_work_items.c.created_at, first_runs.c.first_started_at)
            .select_from(latest_work_items)
            .outerjoin(first_runs, first_runs.c.work_item_id == latest_work_items.c.work_item_id)
        )
        queue_pairs = queue_rows.all()
        queue_delays = [
            max(0.0, (_utc(first_started_at) - _utc(created_at)).total_seconds())
            for created_at, first_started_at in queue_pairs
            if first_started_at is not None
        ]
        queue_without_run = len(queue_pairs) - len(queue_delays)

        oldest_pending_approval = await self._session.scalar(
            select(func.min(ApprovalRequestTable.created_at)).where(
                ApprovalRequestTable.company_id == company_id,
                ApprovalRequestTable.status == "pending",
            )
        )
        pending_approvals = int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(ApprovalRequestTable)
                    .where(
                        ApprovalRequestTable.company_id == company_id,
                        ApprovalRequestTable.status == "pending",
                    )
                )
            )
            or 0
        )

        # A work item contributes once, only while its latest acceptance pointer
        # still names an accepted decision. Repeated/overridden history is ignored.
        current_acceptance_id = WorkItemTable.metadata_json["acceptance_id"].as_string()
        accepted_work_items = (
            select(WorkItemTable.work_item_id.label("work_item_id"))
            .join(
                OutcomeAcceptanceTable,
                and_(
                    OutcomeAcceptanceTable.acceptance_id == current_acceptance_id,
                    OutcomeAcceptanceTable.company_id == WorkItemTable.company_id,
                    OutcomeAcceptanceTable.work_item_id == WorkItemTable.work_item_id,
                    OutcomeAcceptanceTable.verdict == "accepted",
                ),
            )
            .where(
                WorkItemTable.company_id == company_id,
                current_acceptance_id.is_not(None),
            )
            .group_by(WorkItemTable.work_item_id)
            .subquery()
        )
        accepted_count = int(
            (await self._session.scalar(select(func.count()).select_from(accepted_work_items))) or 0
        )

        # Reservations from overlapping budgets are one execution ceiling. Missing
        # reservations and missing actual usage remain visible as coverage gaps.
        estimated_by_execution = (
            select(
                ExecutionReservationTable.execution_id.label("execution_id"),
                func.max(ExecutionReservationTable.amount_usd).label("amount_usd"),
            )
            .join(
                ExecutionLeaseTable,
                ExecutionLeaseTable.execution_id == ExecutionReservationTable.execution_id,
            )
            .where(ExecutionLeaseTable.company_id == company_id)
            .group_by(ExecutionReservationTable.execution_id)
            .subquery()
        )
        estimated_total = await self._session.scalar(
            select(func.coalesce(func.sum(estimated_by_execution.c.amount_usd), 0))
        )
        estimated_execution_count = int(
            (await self._session.scalar(select(func.count()).select_from(estimated_by_execution)))
            or 0
        )
        unestimated_execution_count = int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(ExecutionLeaseTable)
                    .where(
                        ExecutionLeaseTable.company_id == company_id,
                        not_(
                            select(ExecutionReservationTable.execution_id)
                            .where(
                                ExecutionReservationTable.execution_id
                                == ExecutionLeaseTable.execution_id
                            )
                            .exists()
                        ),
                    )
                )
            )
            or 0
        )

        # Explicit execution_id identifies overlapping policy-budget charges. Rows
        # without it remain distinct by usage_id, even when trace_id is shared.
        execution_key = BudgetUsageTable.metadata_json["execution_id"].as_string()
        charge_key = func.coalesce(execution_key, BudgetUsageTable.usage_id)
        charged_ceiling = BudgetUsageTable.metadata_json["charged_ceiling"].as_boolean()
        deduplicated_usage = (
            select(
                BudgetUsageTable.run_id.label("run_id"),
                charge_key.label("charge_key"),
                func.max(BudgetUsageTable.cost_usd).label("cost_usd"),
                func.max(case((charged_ceiling.is_(True), 1), else_=0)).label("charged_ceiling"),
            )
            .where(BudgetUsageTable.company_id == company_id)
            .group_by(BudgetUsageTable.run_id, charge_key)
            .subquery()
        )
        budget_usage_total = await self._session.scalar(
            select(func.coalesce(func.sum(deduplicated_usage.c.cost_usd), 0))
        )
        budget_usage_run_count = int(
            (
                await self._session.scalar(
                    select(func.count(func.distinct(deduplicated_usage.c.run_id))).select_from(
                        deduplicated_usage
                    )
                )
            )
            or 0
        )
        failed_run_cost_total = await self._session.scalar(
            select(func.coalesce(func.sum(AgentRunTable.cost_usd), 0)).where(
                AgentRunTable.company_id == company_id,
                AgentRunTable.status == "failed",
            )
        )
        failed_usage_total = await self._session.scalar(
            select(func.coalesce(func.sum(deduplicated_usage.c.cost_usd), 0))
            .select_from(deduplicated_usage)
            .join(AgentRunTable, AgentRunTable.run_id == deduplicated_usage.c.run_id)
            .where(AgentRunTable.company_id == company_id, AgentRunTable.status == "failed")
        )
        usage_cost_by_run = (
            select(
                deduplicated_usage.c.run_id.label("run_id"),
                func.sum(deduplicated_usage.c.cost_usd).label("usage_cost_usd"),
            )
            .where(deduplicated_usage.c.run_id.is_not(None))
            .group_by(deduplicated_usage.c.run_id)
            .subquery()
        )
        reconciled_run_costs = (
            select(
                AgentRunTable.run_id.label("run_id"),
                case(
                    (
                        AgentRunTable.cost_usd
                        > func.coalesce(usage_cost_by_run.c.usage_cost_usd, 0),
                        AgentRunTable.cost_usd,
                    ),
                    else_=func.coalesce(usage_cost_by_run.c.usage_cost_usd, 0),
                ).label("cost_usd"),
            )
            .outerjoin(usage_cost_by_run, usage_cost_by_run.c.run_id == AgentRunTable.run_id)
            .where(AgentRunTable.company_id == company_id)
            .subquery()
        )
        full_run_cost_total = await self._session.scalar(
            select(func.coalesce(func.sum(reconciled_run_costs.c.cost_usd), 0))
        )
        unattributed_usage_total = await self._session.scalar(
            select(func.coalesce(func.sum(deduplicated_usage.c.cost_usd), 0))
            .select_from(deduplicated_usage)
            .outerjoin(
                AgentRunTable,
                and_(
                    AgentRunTable.run_id == deduplicated_usage.c.run_id,
                    AgentRunTable.company_id == company_id,
                ),
            )
            .where(AgentRunTable.run_id.is_(None))
        )
        run_cost_total = await self._session.scalar(
            select(func.coalesce(func.sum(AgentRunTable.cost_usd), 0)).where(
                AgentRunTable.company_id == company_id,
            )
        )
        charged_ceiling_total = await self._session.scalar(
            select(func.coalesce(func.sum(deduplicated_usage.c.cost_usd), 0)).where(
                deduplicated_usage.c.charged_ceiling == 1
            )
        )
        charged_ceiling_count = int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(deduplicated_usage)
                    .where(deduplicated_usage.c.charged_ceiling == 1)
                )
            )
            or 0
        )
        run_cost_coverage = int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(AgentRunTable)
                    .where(
                        AgentRunTable.company_id == company_id,
                        AgentRunTable.cost_usd > 0,
                    )
                )
            )
            or 0
        )
        unmetered_run_count = int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(AgentRunTable)
                    .where(
                        AgentRunTable.company_id == company_id,
                        AgentRunTable.cost_usd <= 0,
                        not_(
                            select(deduplicated_usage.c.run_id)
                            .where(deduplicated_usage.c.run_id == AgentRunTable.run_id)
                            .exists()
                        ),
                    )
                )
            )
            or 0
        )
        # Reconcile mirror records per run, then retain unassociated usage as its
        # own cost. This preserves disjoint runs represented by different ledgers.
        full_cost_total = float(full_run_cost_total or 0) + float(unattributed_usage_total or 0)

        recovery_lease_filter = or_(
            ExecutionLeaseTable.state == "recovery_required",
            (ExecutionLeaseTable.state == "running")
            & (ExecutionLeaseTable.expires_at <= captured_at),
        )
        lease_count, oldest_lease = (
            await self._session.execute(
                select(func.count(), func.min(ExecutionLeaseTable.created_at)).where(
                    ExecutionLeaseTable.company_id == company_id,
                    recovery_lease_filter,
                )
            )
        ).one()

        # Outbox entries carry their company in the event payload; rows without
        # that context are excluded rather than treated as company-wide.
        outbox_company = ControlPlaneEventOutboxTable.payload["company_id"].as_string()
        outbox_count, oldest_outbox = (
            await self._session.execute(
                select(func.count(), func.min(ControlPlaneEventOutboxTable.created_at)).where(
                    outbox_company == company_id,
                    ControlPlaneEventOutboxTable.status == "pending",
                )
            )
        ).one()

        return {
            "company_id": company_id,
            "as_of_utc": captured_at.isoformat(),
            "export_policy": {
                "retention_days": METRICS_EXPORT_RETENTION_DAYS,
                "applies_to": "exported metric snapshots; live metrics are queried on demand",
            },
            "runs": {
                "total": run_count,
                "by_status": run_counts,
                "success_rate": success_count / terminal_count if terminal_count else None,
                "adapter_errors": int(adapter_errors or 0),
            },
            "queue_delay": {
                "p95_seconds": _p95(queue_delays),
                "sample_size": len(queue_delays),
                "sample_limit": WORK_ITEM_QUEUE_SAMPLE_LIMIT,
                "sampled_work_items": len(queue_pairs),
                "excluded_without_run": queue_without_run,
                "source": "work_item.created_at to first associated agent_run.started_at",
            },
            "approvals": {
                "pending": pending_approvals,
                "oldest_pending_age_seconds": _age_seconds(captured_at, oldest_pending_approval),
            },
            "costs": {
                "accepted_outcome_count": accepted_count,
                "full_cost_usd_total": full_cost_total,
                "full_cost_usd_per_accepted_outcome": (
                    full_cost_total / accepted_count if accepted_count else None
                ),
                "full_cost_basis": "sum per-run max(run cost, deduplicated usage) plus unattributed usage",
                "run_reported_cost_usd_total": float(run_cost_total or 0),
                "deduplicated_budget_usage_usd_total": float(budget_usage_total or 0),
                "failed_run_reported_cost_usd": float(failed_run_cost_total or 0),
                "failed_run_budget_charges_usd": float(failed_usage_total or 0),
                "charged_ceiling_usd_total": float(charged_ceiling_total or 0),
                "charged_ceiling_charge_count": charged_ceiling_count,
                "estimated_ceiling_usd_total": float(estimated_total or 0),
                "estimated_ceiling_usd_per_accepted_outcome": (
                    float(estimated_total or 0) / accepted_count if accepted_count else None
                ),
                "estimated_execution_count": estimated_execution_count,
                "unestimated_execution_count": unestimated_execution_count,
                "budget_usage_run_coverage": budget_usage_run_count,
                "run_cost_coverage": run_cost_coverage,
                "unmetered_run_count": unmetered_run_count,
            },
            "unresolved_execution_leases": {
                "count": int(lease_count or 0),
                "oldest_age_seconds": _age_seconds(captured_at, oldest_lease),
            },
            "pending_outbox": {
                "count": int(outbox_count or 0),
                "oldest_age_seconds": _age_seconds(captured_at, oldest_outbox),
            },
        }


def render_prometheus_metrics(metrics: dict[str, Any]) -> str:
    """Render fixed aggregate names with no company or record labels."""
    values = {
        "control_plane_pending_approval_oldest_age_seconds": metrics["approvals"][
            "oldest_pending_age_seconds"
        ],
        "control_plane_unresolved_execution_leases": metrics["unresolved_execution_leases"][
            "count"
        ],
        "control_plane_pending_outbox_oldest_age_seconds": metrics["pending_outbox"][
            "oldest_age_seconds"
        ],
        "control_plane_adapter_errors_total": metrics["runs"]["adapter_errors"],
        "control_plane_work_queue_delay_p95_seconds": metrics["queue_delay"]["p95_seconds"],
        "control_plane_run_success_rate": metrics["runs"]["success_rate"],
        "control_plane_full_cost_usd_per_accepted_outcome": metrics["costs"][
            "full_cost_usd_per_accepted_outcome"
        ],
    }
    lines: list[str] = []
    for name, value in values.items():
        metric_type = "counter" if name.endswith("_total") else "gauge"
        lines.append(f"# TYPE {name} {metric_type}")
        lines.append(f"{name} {value if value is not None else 'NaN'}")
    return "\n".join(lines) + "\n"
