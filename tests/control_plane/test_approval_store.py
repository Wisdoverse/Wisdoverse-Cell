"""Tests for the dedicated control-plane approval store."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.approval_store import SqlAlchemyControlPlaneApprovalStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.evolution_proposal_store import (
    SqlAlchemyControlPlaneEvolutionProposalStore,
)
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionRolloutState,
    EvolutionTier,
)
from shared.control_plane.tables import AuditEventTable, EvolutionProposalTable
from shared.core.identifiers import ApprovalRequestId, CompanyId


@pytest.mark.asyncio
async def test_approval_store_owns_approval_queries(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    approval_store = SqlAlchemyControlPlaneApprovalStore(db_session)

    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_store", name="Wisdoverse Cell")
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_approval_store",
        )
    )
    approval = await approval_store.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:dev-agent",
            source_agent_id="dev-agent",
            proposed_action="Apply approval store extraction",
            reason="Approval SQL should be owned by the approval store.",
            risk="Approval state changes must remain explicit.",
            rollback_note="Keep repository facade delegation.",
            affected_resources=["control-plane"],
            run_id=run.run_id,
            trace_id="trace_approval_store",
            metadata={"source": "approval-store"},
        )
    )
    await approval_store.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.FINANCE,
            status=ApprovalStatus.APPROVED,
            requested_by="agent:finance",
            source_agent_id="pjm-agent",
            proposed_action="Approve budget",
            reason="Budget approval path stays covered.",
            risk="Incorrect finance approval state.",
            rollback_note="Reopen the approval.",
            affected_resources=["budget"],
            trace_id="trace_approval_store_other",
        )
    )

    rows = await approval_store.list_approvals(
        company_id=CompanyId(company.company_id),
        status=ApprovalStatus.PENDING.value,
        run_id=run.run_id,
        trace_id="trace_approval_store",
    )
    fetched = await approval_store.get_approval(ApprovalRequestId(approval.approval_id))

    assert [row.approval_id for row in rows] == [approval.approval_id]
    assert fetched is not None
    assert fetched.category == ApprovalCategory.TECHNICAL.value
    assert fetched.metadata == {"source": "approval-store"}
    assert not hasattr(fetched, "metadata_json")


@pytest.mark.asyncio
async def test_approval_store_resolves_approval_status(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneApprovalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_resolve", name="Wisdoverse Cell")
    )
    approval = await store.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:qa-agent",
            source_agent_id="qa-agent",
            proposed_action="Promote runtime change",
            reason="Quality gate passed.",
            risk="Runtime behavior changes.",
            rollback_note="Keep current runtime.",
            affected_resources=["runtime"],
        )
    )
    previous_updated_at = approval.updated_at

    resolved = await store.resolve_approval(
        ApprovalRequestId(approval.approval_id),
        status=ApprovalStatus.APPROVED,
        resolved_by="human:cto",
    )
    missing = await store.resolve_approval(
        ApprovalRequestId("appr_missing"),
        status=ApprovalStatus.REJECTED,
        resolved_by="human:cto",
    )

    assert resolved is not None
    assert resolved.status == ApprovalStatus.APPROVED.value
    assert resolved.resolved_by == "human:cto"
    assert resolved.resolved_at is not None
    assert resolved.updated_at >= previous_updated_at
    assert missing is None


@pytest.mark.asyncio
async def test_evolution_proposal_store_syncs_proposal_by_approval(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    approval_store = SqlAlchemyControlPlaneApprovalStore(db_session)
    proposal_store = SqlAlchemyControlPlaneEvolutionProposalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_evolution", name="Wisdoverse Cell")
    )
    approval = await approval_store.request_approval(
        ApprovalRequest(
            company_id=company.company_id,
            category=ApprovalCategory.TECHNICAL,
            requested_by="agent:evolution-module",
            source_agent_id="evolution-module",
            proposed_action="Review L2 routing proposal",
            reason="Reduce routing latency.",
            risk="May alter coordination behavior.",
            rollback_note="Keep current routing.",
            affected_resources=["agent-routing"],
        )
    )
    proposal = EvolutionProposalTable(
        proposal_id="evo_approval_store",
        company_id=company.company_id,
        tier=EvolutionTier.L2.value,
        scope="agent-routing",
        evidence={"p95_latency_ms": 1200},
        expected_benefit="Reduce routing latency",
        risk="May alter coordination behavior.",
        approval_id=approval.approval_id,
    )
    db_session.add(proposal)
    await db_session.flush()

    synced = await proposal_store.update_evolution_proposal_approval_state_by_approval(
        ApprovalRequestId(approval.approval_id),
        approval_state=ApprovalStatus.REJECTED.value,
        rollout_state=EvolutionRolloutState.REJECTED.value,
    )
    missing = await proposal_store.update_evolution_proposal_approval_state_by_approval(
        ApprovalRequestId("appr_missing"),
        approval_state=ApprovalStatus.APPROVED.value,
    )

    assert synced is not None
    assert synced.proposal_id == proposal.proposal_id
    assert synced.approval_state == ApprovalStatus.REJECTED.value
    assert synced.rollout_state == EvolutionRolloutState.REJECTED.value
    assert missing is None


@pytest.mark.asyncio
async def test_approval_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    store = SqlAlchemyControlPlaneApprovalStore(db_session)
    company = await company_store.create_company(
        CompanyContext(company_id="cmp_approval_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="approval.requested",
        target_type="approval",
        target_id="appr_001",
        idempotency_key="appr_001:requested",
        detail={"source": "approval-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    result = await db_session.execute(
        select(AuditEventTable).where(
            AuditEventTable.company_id == company.company_id,
            AuditEventTable.idempotency_key == "appr_001:requested",
        )
    )

    assert first.audit_event_id == second.audit_event_id
    assert len(list(result.scalars().all())) == 1
