"""Tests for control-plane approval use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.approval_gate import ApprovalGate
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.approval_use_cases import resolve_approval
from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.domain.approval_request import InvalidApprovalTransitionError
from shared.control_plane.event_outbox_store import SqlAlchemyControlPlaneEventOutboxStore
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.evolution_proposal_use_cases import (
    apply_approval_resolution_event_to_linked_proposal,
    apply_approval_resolution_to_linked_proposal,
)
from shared.control_plane.models import (
    ApprovalCategory,
    ApprovalStatus,
    CompanyContext,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
)
from shared.core.identifiers import EvolutionProposalId
from shared.schemas.event import Event, EventMetadata, EventTypes


@pytest.mark.asyncio
async def test_resolve_approval_use_case_routes_through_aggregate(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneApprovalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_use_case", name="Wisdoverse Cell")
    )
    approval = await ApprovalGate(store).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:dev-agent",
        source_agent_id="dev-agent",
        proposed_action="Run migration",
        reason="Migration requires approval.",
        risk="Schema changes are high impact.",
        rollback_note="Run downgrade migration.",
        affected_resources=["postgres"],
    )

    decision = await resolve_approval(
        store,
        approval_id=approval.approval_id,
        resolved_by="human:cto",
        approved=True,
    )

    assert decision.approved is True
    assert decision.status == ApprovalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_resolve_approval_use_case_leaves_linked_proposal_to_eventual_handler(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    approval_store = SqlAlchemyControlPlaneApprovalStore(db_session)
    proposal_store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_proposal_effect", name="Wisdoverse Cell")
    )
    approval = await ApprovalGate(approval_store).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:evolution-module",
        source_agent_id="evolution-module",
        proposed_action="Review routing proposal",
        reason="Routing latency should drop.",
        risk="Routing behavior may regress.",
        rollback_note="Keep the current router.",
        affected_resources=["agent-routing"],
    )
    proposal = await proposal_store.create_evolution_proposal(
        EvolutionProposal(
            company_id=company.company_id,
            tier=EvolutionTier.L2,
            scope="agent-routing",
            expected_benefit="Lower routing latency.",
            risk="Routing behavior may regress.",
            approval_id=approval.approval_id,
        )
    )

    decision = await resolve_approval(
        approval_store,
        approval_id=approval.approval_id,
        resolved_by="human:cto",
        approved=False,
    )

    unchanged = await proposal_store.get_evolution_proposal(
        EvolutionProposalId(proposal.proposal_id)
    )
    pending_events = await SqlAlchemyControlPlaneEventOutboxStore(db_session).list_pending()

    assert decision.approved is False
    assert unchanged is not None
    assert unchanged.approval_state == ApprovalStatus.PENDING.value
    assert any(event.event_type == EventTypes.APPROVAL_REJECTED for event in pending_events)

    synced = await apply_approval_resolution_to_linked_proposal(
        proposal_store,
        approval_id=approval.approval_id,
        resolved_by="human:cto",
        approved=False,
    )
    audits = await SqlAlchemyControlPlaneAuditEventStore(db_session).list_audit_events(
        company_id=company.company_id,
        target_type="evolution_proposal",
        target_id=proposal.proposal_id,
    )

    assert synced is not None
    assert synced.approval_state == ApprovalStatus.REJECTED.value
    assert synced.rollout_state == EvolutionRolloutState.REJECTED.value
    assert audits[0].action == EventTypes.EVOLUTION_PROPOSAL_UPDATED
    assert audits[0].detail == {
        "proposal_id": proposal.proposal_id,
        "approval_state": ApprovalStatus.REJECTED.value,
        "approval_id": approval.approval_id,
        "rollout_state": EvolutionRolloutState.REJECTED.value,
    }


@pytest.mark.asyncio
async def test_approval_resolution_event_handler_syncs_linked_evolution_proposal(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    approval_store = SqlAlchemyControlPlaneApprovalStore(db_session)
    proposal_store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_event_handler", name="Wisdoverse Cell")
    )
    approval = await ApprovalGate(approval_store).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:evolution-module",
        source_agent_id="evolution-module",
        proposed_action="Review routing proposal",
        reason="Routing latency should drop.",
        risk="Routing behavior may regress.",
        rollback_note="Keep the current router.",
        affected_resources=["agent-routing"],
    )
    proposal = await proposal_store.create_evolution_proposal(
        EvolutionProposal(
            company_id=company.company_id,
            tier=EvolutionTier.L2,
            scope="agent-routing",
            expected_benefit="Lower routing latency.",
            risk="Routing behavior may regress.",
            approval_id=approval.approval_id,
        )
    )
    event = Event(
        event_type=EventTypes.APPROVAL_GRANTED,
        source_agent="control-plane",
        payload={
            "target_id": approval.approval_id,
            "actor_id": "human:cto",
            "detail": {"status": ApprovalStatus.APPROVED.value},
        },
        metadata=EventMetadata(correlation_id="aud_approval_event"),
    )

    synced = await apply_approval_resolution_event_to_linked_proposal(
        proposal_store,
        event,
    )

    assert synced is not None
    assert synced.proposal_id == proposal.proposal_id
    assert synced.approval_state == ApprovalStatus.APPROVED.value
    assert synced.rollout_state == EvolutionRolloutState.PROPOSED.value


@pytest.mark.asyncio
async def test_resolve_approval_use_case_blocks_illegal_domain_transition(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneApprovalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_use_case_invalid", name="Wisdoverse Cell")
    )
    approval = await ApprovalGate(store).request_approval(
        company_id=company.company_id,
        category=ApprovalCategory.TECHNICAL,
        requested_by="agent:dev-agent",
        source_agent_id="dev-agent",
        proposed_action="Run migration",
        reason="Migration requires approval.",
        risk="Schema changes are high impact.",
        rollback_note="Run downgrade migration.",
        affected_resources=["postgres"],
    )
    await resolve_approval(
        store,
        approval_id=approval.approval_id,
        resolved_by="human:cto",
        approved=True,
    )

    with pytest.raises(InvalidApprovalTransitionError):
        await resolve_approval(
            store,
            approval_id=approval.approval_id,
            resolved_by="human:cfo",
            approved=False,
        )
