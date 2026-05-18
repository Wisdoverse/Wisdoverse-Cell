"""Application use cases for control-plane audit and timeline queries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .audit_timeline_ports import ControlPlaneAuditTimelineStore


@dataclass(frozen=True, slots=True)
class TimelineItem:
    """A typed timeline item assembled from control-plane records."""

    item_type: str
    at: datetime
    data: Any


class TimelineScopeRequiredError(Exception):
    """Raised when a timeline query does not provide a trace or run scope."""


async def list_audit_events(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    trace_id: str | None = None,
    run_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List audit events for one company."""
    return await store.list_audit_events(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )


async def build_timeline(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    trace_id: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> list[TimelineItem]:
    """Build a run-scoped or trace-scoped control-plane timeline."""
    if not trace_id and not run_id:
        raise TimelineScopeRequiredError("trace_id_or_run_id_required")

    runs = await _resolve_timeline_runs(
        store,
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )
    run_ids = [row.run_id for row in runs]
    decisions = await _list_run_scoped_decisions(
        store,
        company_id=company_id,
        run_id=run_id,
        run_ids=run_ids,
        limit=limit,
    )
    artifacts = await _list_run_scoped_artifacts(
        store,
        company_id=company_id,
        run_id=run_id,
        run_ids=run_ids,
        limit=limit,
    )
    audits = await store.list_audit_events(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )
    approvals = await store.list_approvals(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )
    budget_usage = await store.list_budget_usage(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )

    items = [
        TimelineItem(item_type="audit_event", at=row.created_at, data=row)
        for row in audits
    ]
    items.extend(
        TimelineItem(
            item_type="agent_run",
            at=row.completed_at or row.started_at,
            data=row,
        )
        for row in runs
    )
    items.extend(
        TimelineItem(
            item_type="approval",
            at=row.resolved_at or row.created_at,
            data=row,
        )
        for row in approvals
    )
    items.extend(
        TimelineItem(item_type="budget_usage", at=row.created_at, data=row)
        for row in budget_usage
    )
    items.extend(
        TimelineItem(item_type="decision", at=row.updated_at or row.created_at, data=row)
        for row in decisions
    )
    items.extend(
        TimelineItem(item_type="artifact", at=row.created_at, data=row)
        for row in artifacts
    )
    return sorted(items, key=lambda item: _timeline_sort_key(item.at), reverse=True)[:limit]


async def _resolve_timeline_runs(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    trace_id: str | None,
    run_id: str | None,
    limit: int,
) -> list[Any]:
    if run_id:
        run = await store.get_agent_run(run_id)
        if run is not None and run.company_id == company_id:
            return [run]
        return []
    return await store.list_agent_runs(
        company_id=company_id,
        trace_id=trace_id,
        limit=limit,
    )


async def _list_run_scoped_decisions(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    run_id: str | None,
    run_ids: list[str],
    limit: int,
) -> list[Any]:
    if run_id:
        return await store.list_decisions(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )
    if not run_ids:
        return []
    return await store.list_decisions(
        company_id=company_id,
        run_ids=run_ids,
        limit=limit,
    )


async def _list_run_scoped_artifacts(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    run_id: str | None,
    run_ids: list[str],
    limit: int,
) -> list[Any]:
    if run_id:
        return await store.list_artifacts(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )
    if not run_ids:
        return []
    return await store.list_artifacts(
        company_id=company_id,
        run_ids=run_ids,
        limit=limit,
    )


def _timeline_sort_key(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()
