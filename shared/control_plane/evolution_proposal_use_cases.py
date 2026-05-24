"""Application use cases for control-plane evolution proposals."""

from __future__ import annotations

from typing import Any

from shared.core.identifiers import ApprovalRequestId, CompanyId, EvolutionProposalId
from shared.schemas.event import Event, EventTypes

from .approval_gate import ApprovalGate
from .domain.approval_resolution import ApprovalResolutionPolicy
from .domain.events import ControlPlaneDomainEvent
from .domain.evolution_proposal import (
    EvolutionProposal as EvolutionProposalAggregate,
)
from .domain.evolution_proposal import (
    approval_state_is_approved,
    evolution_rollout_state,
    rollout_state_requires_approval,
)
from .domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
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


class ApprovalResolutionEventError(ValueError):
    """Raised when an approval resolution event cannot drive proposal sync."""


async def list_evolution_proposals(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    tier: str | None = None,
    approval_state: str | None = None,
    rollout_state: str | None = None,
    scope: str | None = None,
    limit: int = 100,
) -> list[EvolutionProposal]:
    """List evolution proposals for one company."""
    return await store.list_evolution_proposals(
        company_id=CompanyId(company_id),
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
) -> EvolutionProposal:
    """Return one evolution proposal in a company or raise not found."""
    proposal = await store.get_evolution_proposal(EvolutionProposalId(proposal_id))
    if proposal is None or proposal.company_id != company_id:
        raise EvolutionProposalNotFoundError(proposal_id)
    return proposal


async def create_evolution_proposal_with_audit(
    store: ControlPlaneEvolutionProposalStore,
    proposal: EvolutionProposal,
    *,
    approval_required: bool,
    proposed_by: str,
) -> EvolutionProposal:
    """Create an evolution proposal and record its approval/audit side effects."""
    await _ensure_company(store, proposal.company_id)

    approval_id = proposal.approval_id
    approval_state = ApprovalStatus.PENDING.value
    if approval_id:
        approval = await store.get_approval(ApprovalRequestId(approval_id))
        if approval is None or approval.company_id != proposal.company_id:
            raise EvolutionProposalApprovalNotFoundError(approval_id)
        approval_state = approval.status
    elif approval_required:
        approval = await ApprovalGate(store).request_approval(
            company_id=proposal.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by=f"agent:{proposed_by}",
            source_agent_id=proposed_by,
            proposed_action=(f"Review {proposal.tier} evolution proposal for {proposal.scope}"),
            reason=proposal.expected_benefit,
            risk=proposal.risk,
            rollback_note=("Do not promote the proposal; keep current runtime behavior."),
            affected_resources=[proposal.scope],
        )
        approval_id = approval.approval_id
        approval_state = approval.status

    created = await store.create_evolution_proposal(
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
            target_id=created.proposal_id,
            actor_type="agent",
            actor_id=proposed_by,
            detail={
                "proposal_id": created.proposal_id,
                "tier": created.tier,
                "scope": created.scope,
                "approval_state": created.approval_state,
                "rollout_state": created.rollout_state,
                "approval_id": created.approval_id,
            },
        )
    )
    return created


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
) -> EvolutionProposal:
    """Record an agent-originated evolution proposal and its audit event."""
    await _ensure_company(store, company_id)
    created = await store.create_evolution_proposal(
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
            target_id=created.proposal_id,
            actor_type="agent",
            actor_id=actor_id,
            trace_id=trace_id,
            detail={
                "proposal_id": created.proposal_id,
                "tier": created.tier,
                "scope": created.scope,
                "approval_state": created.approval_state,
                "rollout_state": created.rollout_state,
                "approval_id": created.approval_id,
            },
        )
    )
    return created


async def update_evolution_proposal_status_with_audit(
    store: ControlPlaneEvolutionProposalStore,
    *,
    company_id: str,
    proposal_id: str,
    approval_state: ApprovalStatus | str | None,
    rollout_state: EvolutionRolloutState | str | None,
    approval_id: str | None,
    actor_id: str,
) -> EvolutionProposal:
    """Update an evolution proposal status and record its audit event."""
    proposal_identifier = EvolutionProposalId(proposal_id)
    existing = await store.get_evolution_proposal(proposal_identifier)
    if existing is None or existing.company_id != company_id:
        raise EvolutionProposalNotFoundError(proposal_id)

    approval_state_value = _enum_value(approval_state)
    rollout_state_value = _enum_value(rollout_state)
    rollout_state_target = evolution_rollout_state(rollout_state_value)
    approval_identifier = ApprovalRequestId(approval_id) if approval_id else None
    if approval_id:
        approval = await store.get_approval(approval_identifier)
        if approval is None or approval.company_id != company_id:
            raise EvolutionProposalApprovalNotFoundError(approval_id)
        approval_state_value = approval_state_value or approval.status

    effective_approval_state = approval_state_value or existing.approval_state
    if rollout_state_requires_approval(rollout_state_target) and not approval_state_is_approved(
        effective_approval_state
    ):
        raise EvolutionProposalApprovalRequiredError(proposal_id)

    domain_events: list[ControlPlaneDomainEvent] = []
    if rollout_state_target is not None:
        aggregate = EvolutionProposalAggregate.from_record(existing)
        aggregate.advance_rollout(rollout_state_target)
        domain_events = aggregate.pull_events()
        rollout_state_value = aggregate.rollout_state.value

    updated = await store.update_evolution_proposal_status(
        proposal_identifier,
        approval_state=approval_state_value,
        rollout_state=rollout_state_value,
        approval_id=approval_identifier,
    )
    if updated is None:
        raise EvolutionProposalNotFoundError(proposal_id)

    detail = {
        "proposal_id": updated.proposal_id,
        "approval_state": updated.approval_state,
        "rollout_state": updated.rollout_state,
        "approval_id": updated.approval_id,
    }
    if domain_events:
        await append_control_plane_domain_event_audits(
            store,
            domain_events,
            DomainEventAuditContext(
                actor_type="user",
                actor_id=actor_id,
                detail=detail,
            ),
        )
        return updated

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.EVOLUTION_PROPOSAL_UPDATED,
            target_type="evolution_proposal",
            target_id=updated.proposal_id,
            actor_type="user",
            actor_id=actor_id,
            detail=detail,
        )
    )
    return updated


async def apply_approval_resolution_to_linked_proposal(
    store: ControlPlaneEvolutionProposalStore,
    *,
    approval_id: str,
    approved: bool,
    resolved_by: str,
) -> EvolutionProposal | None:
    """Apply a resolved approval to a linked evolution proposal in its own transaction."""
    effect = ApprovalResolutionPolicy().resolve(approved=approved)
    proposal = await store.update_evolution_proposal_approval_state_by_approval(
        ApprovalRequestId(approval_id),
        **effect.proposal_update_kwargs(),
    )
    if proposal is None:
        return None

    await store.append_audit_event(
        AuditEvent(
            company_id=proposal.company_id,
            action=EventTypes.EVOLUTION_PROPOSAL_UPDATED,
            target_type="evolution_proposal",
            target_id=proposal.proposal_id,
            actor_type="user",
            actor_id=resolved_by,
            detail=effect.proposal_audit_detail(
                proposal_id=proposal.proposal_id,
                approval_id=approval_id,
            ),
        )
    )
    return proposal


async def apply_approval_resolution_event_to_linked_proposal(
    store: ControlPlaneEvolutionProposalStore,
    event: Event,
) -> EvolutionProposal | None:
    """Apply an approval.granted/rejected event to a linked evolution proposal."""
    if event.event_type not in {
        EventTypes.APPROVAL_GRANTED,
        EventTypes.APPROVAL_REJECTED,
    }:
        raise ApprovalResolutionEventError(
            f"unsupported approval resolution event: {event.event_type}"
        )

    approval_id = _approval_id_from_event(event)
    resolved_by = str(event.payload.get("actor_id") or "system")
    return await apply_approval_resolution_to_linked_proposal(
        store,
        approval_id=approval_id,
        approved=event.event_type == EventTypes.APPROVAL_GRANTED,
        resolved_by=resolved_by,
    )


async def _ensure_company(
    store: ControlPlaneEvolutionProposalStore,
    company_id: str,
) -> None:
    if await store.get_company(CompanyId(company_id)) is not None:
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


def _approval_id_from_event(event: Event) -> str:
    approval_id = event.payload.get("target_id")
    if approval_id:
        return str(approval_id)

    detail = event.payload.get("detail")
    if isinstance(detail, dict) and detail.get("approval_id"):
        return str(detail["approval_id"])

    raise ApprovalResolutionEventError("approval resolution event missing approval_id")
