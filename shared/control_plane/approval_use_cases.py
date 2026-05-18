"""Approval use cases shared by control-plane HTTP adapters."""
from __future__ import annotations

from shared.schemas.event import EventTypes

from .approval_gate import ApprovalDecision, ApprovalGate
from .approval_ports import ControlPlaneApprovalStore
from .models import ApprovalStatus, AuditEvent, EvolutionRolloutState


async def resolve_approval_and_sync_proposal(
    store: ControlPlaneApprovalStore,
    *,
    approval_id: str,
    resolved_by: str,
    approved: bool,
) -> ApprovalDecision:
    """Resolve an approval and sync any tied evolution proposal."""
    gate = ApprovalGate(store)
    if approved:
        decision = await gate.approve(approval_id, resolved_by=resolved_by)
        proposal = await store.update_evolution_proposal_approval_state_by_approval(
            approval_id,
            approval_state=ApprovalStatus.APPROVED.value,
        )
    else:
        decision = await gate.reject(approval_id, resolved_by=resolved_by)
        proposal = await store.update_evolution_proposal_approval_state_by_approval(
            approval_id,
            approval_state=ApprovalStatus.REJECTED.value,
            rollout_state=EvolutionRolloutState.REJECTED.value,
        )

    if proposal is not None:
        detail = {
            "proposal_id": proposal.proposal_id,
            "approval_state": proposal.approval_state,
            "approval_id": approval_id,
        }
        if not approved:
            detail["rollout_state"] = proposal.rollout_state
        await store.append_audit_event(
            AuditEvent(
                company_id=proposal.company_id,
                action=EventTypes.EVOLUTION_PROPOSAL_UPDATED,
                target_type="evolution_proposal",
                target_id=proposal.proposal_id,
                actor_type="user",
                actor_id=resolved_by,
                detail=detail,
            )
        )

    return decision
