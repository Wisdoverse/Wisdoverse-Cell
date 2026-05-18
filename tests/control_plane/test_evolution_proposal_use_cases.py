"""Tests for control-plane evolution proposal use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.evolution_proposal_use_cases import (
    record_evolution_proposal_with_audit,
)
from shared.control_plane.models import ApprovalStatus, EvolutionTier
from shared.control_plane.repository import ControlPlaneRepository
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

    repo = ControlPlaneRepository(db_session)
    company = await repo.get_company("cmp_agent_evolution")
    proposal = await repo.get_evolution_proposal(row.proposal_id)
    audit_events = await repo.list_audit_events(
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
