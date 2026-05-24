"""Tests for control-plane evolution proposal use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.domain.evolution_proposal import (
    InvalidEvolutionRolloutTransitionError,
)
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.evolution_proposal_use_cases import (
    EvolutionProposalApprovalRequiredError,
    record_evolution_proposal_with_audit,
    update_evolution_proposal_status_with_audit,
)
from shared.control_plane.models import (
    ApprovalStatus,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
)
from shared.core.identifiers import CompanyId, EvolutionProposalId
from shared.schemas.event import EventTypes


@pytest.mark.asyncio
async def test_record_evolution_proposal_with_audit_preserves_agent_context(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)

    row = await record_evolution_proposal_with_audit(
        store,
        company_id="cmp_agent_evolution",
        tier=EvolutionTier.L2,
        scope="agent:requirement-manager",
        evidence={"source_agent": "evolution-module"},
        expected_benefit="Reduce repeated planning errors.",
        risk="Incorrect recommendation could regress workflow quality.",
        approval_state=ApprovalStatus.PENDING.value,
        approval_id=None,
        metadata={"operation": "architecture_review"},
        actor_id="evolution-module",
        trace_id="trace-evolution-proposal",
    )

    audits = SqlAlchemyControlPlaneAuditEventStore(db_session)
    company = await store.get_company(CompanyId("cmp_agent_evolution"))
    proposal = await store.get_evolution_proposal(EvolutionProposalId(row.proposal_id))
    audit_events = await audits.list_audit_events(
        company_id="cmp_agent_evolution",
        trace_id="trace-evolution-proposal",
        target_type="evolution_proposal",
        target_id=row.proposal_id,
    )

    assert company is not None
    assert proposal is not None
    assert proposal.approval_state == ApprovalStatus.PENDING.value
    assert proposal.scope == "agent:requirement-manager"
    assert len(audit_events) == 1
    assert audit_events[0].action == EventTypes.EVOLUTION_PROPOSAL_CREATED
    assert audit_events[0].actor_id == "evolution-module"
    assert audit_events[0].detail["approval_id"] is None


@pytest.mark.asyncio
async def test_update_evolution_proposal_status_enforces_domain_rollout_policy(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)
    proposal = await store.create_evolution_proposal(
        EvolutionProposal(
            company_id="cmp_evolution_rollout_policy",
            tier=EvolutionTier.L2,
            scope="agent-routing",
            expected_benefit="Reduce routing latency.",
            risk="Canary may affect dispatch quality.",
        )
    )

    with pytest.raises(EvolutionProposalApprovalRequiredError):
        await update_evolution_proposal_status_with_audit(
            store,
            company_id="cmp_evolution_rollout_policy",
            proposal_id=proposal.proposal_id,
            approval_state=None,
            rollout_state=EvolutionRolloutState.CANARY,
            approval_id=None,
            actor_id="human:architect",
        )

    with pytest.raises(InvalidEvolutionRolloutTransitionError):
        await update_evolution_proposal_status_with_audit(
            store,
            company_id="cmp_evolution_rollout_policy",
            proposal_id=proposal.proposal_id,
            approval_state=ApprovalStatus.APPROVED,
            rollout_state=EvolutionRolloutState.ACTIVE,
            approval_id=None,
            actor_id="human:architect",
        )

    canary = await update_evolution_proposal_status_with_audit(
        store,
        company_id="cmp_evolution_rollout_policy",
        proposal_id=proposal.proposal_id,
        approval_state=ApprovalStatus.APPROVED,
        rollout_state=EvolutionRolloutState.CANARY,
        approval_id=None,
        actor_id="human:architect",
    )
    active = await update_evolution_proposal_status_with_audit(
        store,
        company_id="cmp_evolution_rollout_policy",
        proposal_id=proposal.proposal_id,
        approval_state=None,
        rollout_state=EvolutionRolloutState.ACTIVE,
        approval_id=None,
        actor_id="human:architect",
    )

    assert canary.rollout_state == EvolutionRolloutState.CANARY.value
    assert active.rollout_state == EvolutionRolloutState.ACTIVE.value
