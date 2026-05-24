"""Approval use cases shared by control-plane HTTP adapters."""

from __future__ import annotations

from shared.core.identifiers import CompanyId

from .approval_gate import ApprovalDecision, ApprovalGate
from .approval_ports import ControlPlaneApprovalStore
from .models import ApprovalRequest


async def list_approvals(
    store: ControlPlaneApprovalStore,
    *,
    company_id: str,
    status: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    work_item_id: str | None = None,
    limit: int = 50,
) -> list[ApprovalRequest]:
    """List approval requests for one company."""
    return await store.list_approvals(
        company_id=CompanyId(company_id),
        status=status,
        run_id=run_id,
        trace_id=trace_id,
        work_item_id=work_item_id,
        limit=limit,
    )


async def resolve_approval(
    store: ControlPlaneApprovalStore,
    *,
    approval_id: str,
    resolved_by: str,
    approved: bool,
) -> ApprovalDecision:
    """Resolve one approval request through the ApprovalRequest aggregate."""
    gate = ApprovalGate(store)
    if approved:
        return await gate.approve(approval_id, resolved_by=resolved_by)
    return await gate.reject(approval_id, resolved_by=resolved_by)
