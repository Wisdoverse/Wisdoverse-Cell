"""Tests for the control-plane evolution proposal store."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.models import (
    ApprovalCategory,
    ApprovalRequest,
    ApprovalStatus,
    CompanyContext,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
)


@pytest.mark.asyncio
async def test_evolution_proposal_store_owns_proposal_lifecycle(
    db_session: AsyncSession,
):
    store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)
    company = await store.create_company(CompanyContext(name="Wisdoverse Cell"))
    approval = await store.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:evolution-module",
            source_agent_id="evolution-module",
            proposed_action="Review routing evolution",
            reason="Reduce queue latency",
            risk="Routing behavior can change",
            rollback_note="Keep existing routing",
            affected_resources=["agent-routing"],
        )
    )
    proposal = await store.create_evolution_proposal(
        EvolutionProposal(
            company_id=company.company_id,
            tier=EvolutionTier.L2,
            scope="agent-routing",
            evidence={"p95_latency_ms": 1200},
            expected_benefit="Reduce queue latency",
            risk="Routing behavior can change",
            approval_id=approval.approval_id,
        )
    )

    listed = await store.list_evolution_proposals(
        company_id=company.company_id,
        tier=EvolutionTier.L2.value,
        approval_state=ApprovalStatus.PENDING.value,
        scope="routing",
    )
    shadowed = await store.update_evolution_proposal_status(
        proposal.proposal_id,
        rollout_state=EvolutionRolloutState.SHADOW.value,
    )
    approved = await store.update_evolution_proposal_approval_state_by_approval(
        approval.approval_id,
        approval_state=ApprovalStatus.APPROVED.value,
    )

    assert [row.proposal_id for row in listed] == [proposal.proposal_id]
    assert shadowed is not None
    assert shadowed.rollout_state == EvolutionRolloutState.SHADOW.value
    assert approved is not None
    assert approved.approval_state == ApprovalStatus.APPROVED.value
