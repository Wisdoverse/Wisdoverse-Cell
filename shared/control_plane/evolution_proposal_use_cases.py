"""Application use cases for control-plane evolution proposals."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .approval_gate import ApprovalGate
from .evolution_proposal_ports import ControlPlaneEvolutionProposalStore
from .models import (
    ApprovalCategory,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
)


class EvolutionProposalApprovalNotFoundError(Exception):
    """Raised when a linked approval is missing or belongs to another company."""


class EvolutionProposalApprovalRequiredError(Exception):
    """Raised when rollout requires an approved approval."""


class EvolutionProposalNotFoundError(Exception):
    """Raised when an evolution proposal cannot be found in the target company."""


async def list_evolution_proposals(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    tier: str | None = None,
    approval_state: str | None = None,
    rollout_state: str | None = None,
    scope: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List evolution proposals for one company."""
    return await store.list_evolution_proposals(
        company_id=company_id,
        tier=tier,
        approval_state=approval_state,
        rollout_state=rollout_state,
        scope=scope,
        limit=limit,
    )


async def get_evolution_proposal(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    proposal_id: str,
) -> Any:
    """Return one evolution proposal in a company or raise not found."""
    row = await store.get_evolution_proposal(proposal_id)
    if row is None or row.company_id != company_id:
        raise EvolutionProposalNotFoundError(proposal_id)
    return row


async def create_evolution_proposal_with_audit(
    store: ControlPlaneEvolutionProposalStore,
    proposal: EvolutionProposal,
    *,
    approval_required: bool,
    proposed_by: str,
) -> Any:
    """Create an evolution proposal and record its approval/audit side effects."""
    await _ensure_company(store, proposal.company_id)

    approval_id = proposal.approval_id
    approval_state = ApprovalStatus.PENDING.value
    if approval_id:
        approval = await store.get_approval(approval_id)
        if approval is None or approval.company_id != proposal.company_id:
            raise EvolutionProposalApprovalNotFoundError(approval_id)
        approval_state = approval.status
    elif approval_required:
        approval = await ApprovalGate(store).request_approval(
            company_id=proposal.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by=f"agent:{proposed_by}",
            source_agent_id=proposed_by,
            proposed_action=(
                f"Review {proposal.tier} evolution proposal for {proposal.scope}"
            ),
            reason=proposal.expected_benefit,
            risk=proposal.risk,
            rollback_note=(
                "Do not promote the proposal; keep current runtime behavior."
            ),
            affected_resources=[proposal.scope],
        )
        approval_id = approval.approval_id
        approval_state = approval.status

    row = await store.create_evolution_proposal(
        proposal.model_copy(
            update={
                "approval_state": approval_state,
                "approval_id": approval_id,
            }
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=proposal.company_id,
            action=EventTypes.EVOLUTION_PROPOSAL_CREATED,
            target_type="evolution_proposal",
            target_id=row.proposal_id,
            actor_type="agent",
            actor_id=proposed_by,
            detail={
                "proposal_id": row.proposal_id,
                "tier": row.tier,
                "scope": row.scope,
                "approval_state": row.approval_state,
                "rollout_state": row.rollout_state,
                "approval_id": row.approval_id,
            },
        )
    )
    return row


async def ensure_evolution_proposal_company(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
) -> None:
    """Ensure the company context used by evolution proposal records exists."""
    await _ensure_company(store, company_id)


async def record_evolution_proposal_with_audit(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    tier: EvolutionTier,
    scope: str,
    evidence: dict[str, Any],
    expected_benefit: str,
    risk: str,
    approval_state: str,
    approval_id: str | None,
    metadata: dict[str, Any],
    actor_id: str,
    trace_id: str | None,
) -> Any:
    """Record an agent-originated evolution proposal and its audit event."""
    await _ensure_company(store, company_id)
    row = await store.create_evolution_proposal(
        EvolutionProposal(
            company_id=company_id,
            tier=tier,
            scope=scope,
            evidence=evidence,
            expected_benefit=expected_benefit,
            risk=risk,
            approval_state=approval_state,
            approval_id=approval_id,
            metadata=metadata,
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.EVOLUTION_PROPOSAL_CREATED,
            target_type="evolution_proposal",
            target_id=row.proposal_id,
            actor_type="agent",
            actor_id=actor_id,
            trace_id=trace_id,
            detail={
                "proposal_id": row.proposal_id,
                "tier": row.tier,
                "scope": row.scope,
                "approval_state": row.approval_state,
                "rollout_state": row.rollout_state,
                "approval_id": row.approval_id,
            },
        )
    )
    return row


async def update_evolution_proposal_status_with_audit(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    proposal_id: str,
    approval_state: ApprovalStatus | str | None,
    rollout_state: EvolutionRolloutState | str | None,
    approval_id: str | None,
    actor_id: str,
) -> Any:
    """Update an evolution proposal status and record its audit event."""
    existing = await store.get_evolution_proposal(proposal_id)
    if existing is None or existing.company_id != company_id:
        raise EvolutionProposalNotFoundError(proposal_id)

    approval_state_value = _enum_value(approval_state)
    rollout_state_value = _enum_value(rollout_state)
    if approval_id:
        approval = await store.get_approval(approval_id)
        if approval is None or approval.company_id != company_id:
            raise EvolutionProposalApprovalNotFoundError(approval_id)
        approval_state_value = approval_state_value or approval.status

    effective_approval_state = approval_state_value or existing.approval_state
    if (
        _rollout_requires_approval(rollout_state_value)
        and effective_approval_state != ApprovalStatus.APPROVED.value
    ):
        raise EvolutionProposalApprovalRequiredError(proposal_id)

    row = await store.update_evolution_proposal_status(
        proposal_id,
        approval_state=approval_state_value,
        rollout_state=rollout_state_value,
        approval_id=approval_id,
    )
    if row is None:
        raise EvolutionProposalNotFoundError(proposal_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.EVOLUTION_PROPOSAL_UPDATED,
            target_type="evolution_proposal",
            target_id=row.proposal_id,
            actor_type="user",
            actor_id=actor_id,
            detail={
                "proposal_id": row.proposal_id,
                "approval_state": row.approval_state,
                "rollout_state": row.rollout_state,
                "approval_id": row.approval_id,
            },
        )
    )
    return row


async def _ensure_company(
    store: ControlPlaneEvolutionProposalStore,
    company_id: str,
) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _rollout_requires_approval(rollout_state: str | None) -> bool:
    return rollout_state in {
        EvolutionRolloutState.CANARY.value,
        EvolutionRolloutState.ACTIVE.value,
    }
