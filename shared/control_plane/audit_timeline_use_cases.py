"""Application use cases for control-plane audit and timeline queries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .audit_timeline_ports import ControlPlaneAuditTimelineStore
from .domain_records import (
    agent_run_record,
    approval_request_record,
    artifact_record,
    audit_event_record,
    budget_usage_record,
    decision_record,
)
from .models import AgentRun, Artifact, AuditEvent, Decision


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
) -> list[AuditEvent]:
    """List audit events for one company."""
    rows = await store.list_audit_events(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    return [audit_event_record(row) for row in rows]


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
    audit_rows = await store.list_audit_events(
        company_id=company_id,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
    )
    approvals = [
        approval_request_record(row)
        for row in await store.list_approvals(
            company_id=company_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )
    ]
    budget_usage = [
        budget_usage_record(row)
        for row in await store.list_budget_usage(
            company_id=company_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )
    ]
    audits = [audit_event_record(row) for row in audit_rows]

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
) -> list[AgentRun]:
    if run_id:
        row = await store.get_agent_run(run_id)
        if row is not None and row.company_id == company_id:
            return [agent_run_record(row)]
        return []
    rows = await store.list_agent_runs(
        company_id=company_id,
        trace_id=trace_id,
        limit=limit,
    )
    return [agent_run_record(row) for row in rows]


async def _list_run_scoped_decisions(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    run_id: str | None,
    run_ids: list[str],
    limit: int,
) -> list[Decision]:
    if run_id:
        rows = await store.list_decisions(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )
        return [decision_record(row) for row in rows]
    if not run_ids:
        return []
    rows = await store.list_decisions(
        company_id=company_id,
        run_ids=run_ids,
        limit=limit,
    )
    return [decision_record(row) for row in rows]


async def _list_run_scoped_artifacts(
    store: ControlPlaneAuditTimelineStore,
    *,
    company_id: str,
    run_id: str | None,
    run_ids: list[str],
    limit: int,
) -> list[Artifact]:
    if run_id:
        rows = await store.list_artifacts(
            company_id=company_id,
            run_id=run_id,
            limit=limit,
        )
        return [artifact_record(row) for row in rows]
    if not run_ids:
        return []
    rows = await store.list_artifacts(
        company_id=company_id,
        run_ids=run_ids,
        limit=limit,
    )
    return [artifact_record(row) for row in rows]


def _timeline_sort_key(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()
